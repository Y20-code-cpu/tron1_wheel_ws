#ifndef WEBSOCKET_CLIENT_H
#define WEBSOCKET_CLIENT_H

#include <string>
#include <functional>
#include <websocketpp/client.hpp>
#include <websocketpp/config/asio_no_tls.hpp>

typedef websocketpp::client<websocketpp::config::asio> WebSocketClient;
typedef websocketpp::connection_hdl ConnectionHandle;

class WebSocketManager {
public:
    WebSocketManager();
    ~WebSocketManager();
    
    // 连接到机器人WebSocket服务
    bool connect(const std::string& uri);
    
    // 断开连接
    void disconnect();
    
    // 发送消息
    bool send(const std::string& message);
    
    // 设置消息接收回调
    void setMessageCallback(std::function<void(const std::string&)> callback);
    
    // 检查连接状态
    bool isConnected() const { return m_connected; }
    
private:
    WebSocketClient m_client;
    ConnectionHandle m_connection_hdl;
    bool m_connected;
    std::function<void(const std::string&)> m_message_callback;
    
    // WebSocket事件处理
    void onOpen(ConnectionHandle hdl);
    void onClose(ConnectionHandle hdl);
    void onMessage(ConnectionHandle hdl, WebSocketClient::message_ptr msg);
    void onFail(ConnectionHandle hdl);
};

#endif // WEBSOCKET_CLIENT_H