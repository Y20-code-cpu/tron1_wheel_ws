#include <ros/ros.h>
#include <geometry_msgs/Twist.h>
#include <sensor_msgs/Imu.h>
#include <std_msgs/String.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <thread>
#include <atomic>
#include "tron1_controller/websocket_client.h"

using json = nlohmann::json;

class Tron1Controller {
public:
    Tron1Controller() : m_running(true) {
        // 初始化ROS节点
        ros::NodeHandle nh;
        ros::NodeHandle pnh("~");
        
        // 读取参数
        pnh.param<std::string>("robot_ip", m_robot_ip, "10.192.1.2");
        pnh.param<std::string>("robot_accid", m_robot_accid, "");
        pnh.param<double>("control_rate", m_control_rate, 50.0);  // 50Hz
        
        // 订阅速度指令
        m_cmd_sub = nh.subscribe("/cmd_vel", 10, &Tron1Controller::cmdVelCallback, this);
        
        // 发布机器人状态
        m_state_pub = nh.advertise<std_msgs::String>("/tron1/state", 10);
        m_imu_pub = nh.advertise<sensor_msgs::Imu>("/tron1/imu", 10);
        
        // 初始化WebSocket客户端
        m_ws_client = std::make_unique<WebSocketManager>();
        m_ws_client->setMessageCallback(std::bind(&Tron1Controller::onWebSocketMessage, this, 
                                                   std::placeholders::_1));
        
        // 启动控制循环
        m_control_thread = std::thread(&Tron1Controller::controlLoop, this);
    }
    
    ~Tron1Controller() {
        m_running = false;
        if (m_control_thread.joinable()) {
            m_control_thread.join();
        }
        if (m_ws_client) {
            m_ws_client->disconnect();
        }
    }
    
    bool connect() {
        std::string uri = "ws://" + m_robot_ip + ":5000";
        ROS_INFO("Connecting to robot at %s", uri.c_str());
        
        if (!m_ws_client->connect(uri)) {
            ROS_ERROR("Failed to connect to robot");
            return false;
        }
        
        ROS_INFO("Connected to robot");
        
        // 发送初始指令：开启IMU数据
        json enable_imu = {
            {"title", "request_enable_imu"},
            {"data", {{"enable", true}}}
        };
        sendCommand(enable_imu);
        
        // 等待1秒让机器人准备
        std::this_thread::sleep_for(std::chrono::seconds(1));
        
        // 发送站起指令
        json stand_cmd = {
            {"title", "request_stand_mode"},
            {"data", {}}
        };
        sendCommand(stand_cmd);
        
        return true;
    }
    
private:
    void cmdVelCallback(const geometry_msgs::Twist::ConstPtr& msg) {
        // 缓存最新的速度指令
        std::lock_guard<std::mutex> lock(m_cmd_mutex);
        m_current_cmd = *msg;
    }
    
    void sendCommand(const json& command) {
        if (!m_ws_client || !m_ws_client->isConnected()) {
            ROS_WARN("WebSocket not connected, cannot send command");
            return;
        }
        
        json full_cmd = command;
        
        // 添加标准字段
        if (!full_cmd.contains("accid") && !m_robot_accid.empty()) {
            full_cmd["accid"] = m_robot_accid;
        }
        
        if (!full_cmd.contains("timestamp")) {
            auto now = std::chrono::system_clock::now();
            auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
                now.time_since_epoch()).count();
            full_cmd["timestamp"] = timestamp;
        }
        
        if (!full_cmd.contains("guid")) {
            // 生成简单的GUID
            auto now = std::chrono::system_clock::now();
            full_cmd["guid"] = std::to_string(now.time_since_epoch().count());
        }
        
        m_ws_client->send(full_cmd.dump());
    }
    
    void sendTwistCommand(const geometry_msgs::Twist& twist) {
        json twist_cmd = {
            {"title", "request_twist"},
            {"data", {
                {"x", twist.linear.x},
                {"y", twist.linear.y},
                {"z", twist.angular.z}
            }}
        };
        sendCommand(twist_cmd);
    }
    
    void controlLoop() {
        ros::Rate rate(m_control_rate);
        
        while (m_running && ros::ok()) {
            if (m_ws_client && m_ws_client->isConnected()) {
                // 发送当前速度指令
                std::lock_guard<std::mutex> lock(m_cmd_mutex);
                sendTwistCommand(m_current_cmd);
            }
            rate.sleep();
        }
    }
    
    void onWebSocketMessage(const std::string& message) {
        try {
            json msg = json::parse(message);
            
            std::string title = msg.value("title", "");
            
            if (title == "notify_imu") {
                // 处理IMU数据
                if (msg.contains("data")) {
                    auto& data = msg["data"];
                    
                    sensor_msgs::Imu imu_msg;
                    imu_msg.header.stamp = ros::Time::now();
                    imu_msg.header.frame_id = "imu_link";
                    
                    if (data.contains("acc")) {
                        imu_msg.linear_acceleration.x = data["acc"][0];
                        imu_msg.linear_acceleration.y = data["acc"][1];
                        imu_msg.linear_acceleration.z = data["acc"][2];
                    }
                    
                    if (data.contains("gyro")) {
                        imu_msg.angular_velocity.x = data["gyro"][0];
                        imu_msg.angular_velocity.y = data["gyro"][1];
                        imu_msg.angular_velocity.z = data["gyro"][2];
                    }
                    
                    if (data.contains("quat")) {
                        imu_msg.orientation.w = data["quat"][0];
                        imu_msg.orientation.x = data["quat"][1];
                        imu_msg.orientation.y = data["quat"][2];
                        imu_msg.orientation.z = data["quat"][3];
                    }
                    
                    m_imu_pub.publish(imu_msg);
                }
            }
            else if (title == "notify_robot_info") {
                // 发布机器人状态
                std_msgs::String state_msg;
                state_msg.data = message;
                m_state_pub.publish(state_msg);
                
                // 输出状态信息
                if (msg.contains("data")) {
                    auto& data = msg["data"];
                    if (data.contains("status")) {
                        ROS_INFO("Robot status: %s", data["status"].get<std::string>().c_str());
                    }
                    if (data.contains("battery")) {
                        ROS_INFO("Battery: %d%%", data["battery"].get<int>());
                    }
                }
            }
            else if (title.find("response_") == 0) {
                // 处理响应消息
                if (msg.contains("data") && msg["data"].contains("result")) {
                    std::string result = msg["data"]["result"];
                    ROS_INFO("Command response: %s", result.c_str());
                }
            }
            else {
                ROS_DEBUG("Received message: %s", title.c_str());
            }
            
        } catch (const std::exception& e) {
            ROS_ERROR("Failed to parse message: %s", e.what());
        }
    }
    
private:
    std::unique_ptr<WebSocketManager> m_ws_client;
    std::string m_robot_ip;
    std::string m_robot_accid;
    double m_control_rate;
    std::atomic<bool> m_running;
    std::thread m_control_thread;
    
    geometry_msgs::Twist m_current_cmd;
    std::mutex m_cmd_mutex;
    
    ros::Subscriber m_cmd_sub;
    ros::Publisher m_state_pub;
    ros::Publisher m_imu_pub;
};

int main(int argc, char** argv) {
    ros::init(argc, argv, "tron1_controller");
    
    Tron1Controller controller;
    
    // 连接到机器人
    if (!controller.connect()) {
        ROS_ERROR("Failed to connect to robot, exiting...");
        return 1;
    }
    
    ros::spin();
    
    return 0;
}