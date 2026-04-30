#include "tron1_controller/websocket_client.h"
#include <iostream>
#include <websocketpp/common/asio.hpp>

WebSocketManager::WebSocketManager() : m_connected(false) {
    // 初始化WebSocket客户端
    m_client.init_asio();
    m_client.set_open_handler(std::bind(&WebSocketManager::onOpen, this, std::placeholders::_1));
    m_client.set_close_handler(std::bind(&WebSocketManager::onClose, this, std::placeholders::_1));
    m_client.set_message_handler(std::bind(&WebSocketManager::onMessage, this, 
                                            std::placeholders::_1, std::placeholders::_2));
    m_client.set_fail_handler(std::bind(&WebSocketManager::onFail, this, std::placeholders::_1));
}

WebSocketManager::~WebSocketManager() {
    disconnect();
}

bool WebSocketManager::connect(const std::string& uri) {
    try {
        websocketpp::lib::error_code ec;
        WebSocketClient::connection_ptr con = m_client.get_connection(uri, ec);
        
        if (ec) {
            std::cerr << "Connection error: " << ec.message() << std::endl;
            return false;
        }
        
        m_connection_hdl = con->get_handle();
        m_client.connect(con);
        
        // 在单独的线程中运行WebSocket客户端
        std::thread([this]() {
            m_client.run();
        }).detach();
        
        // 等待连接建立
        for (int i = 0; i < 50 && !m_connected; i++) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        
        return m_connected;
        
    } catch (const std::exception& e) {
        std::cerr << "Connect exception: " << e.what() << std::endl;
        return false;
    }
}

void WebSocketManager::disconnect() {
    if (m_connected) {
        m_client.stop();
        m_connected = false;
    }
}

bool WebSocketManager::send(const std::string& message) {
    if (!m_connected) {
        std::cerr << "Not connected to robot" << std::endl;
        return false;
    }
    
    try {
        websocketpp::lib::error_code ec;
        m_client.send(m_connection_hdl, message, websocketpp::frame::opcode::text, ec);
        
        if (ec) {
            std::cerr << "Send error: " << ec.message() << std::endl;
            return false;
        }
        
        return true;
        
    } catch (const std::exception& e) {
        std::cerr << "Send exception: " << e.what() << std::endl;
        return false;
    }
}

void WebSocketManager::setMessageCallback(std::function<void(const std::string&)> callback) {
    m_message_callback = callback;
}

void WebSocketManager::onOpen(ConnectionHandle hdl) {
    std::cout << "WebSocket connection opened" << std::endl;
    m_connected = true;
}

void WebSocketManager::onClose(ConnectionHandle hdl) {
    std::cout << "WebSocket connection closed" << std::endl;
    m_connected = false;
}

void WebSocketManager::onMessage(ConnectionHandle hdl, WebSocketClient::message_ptr msg) {
    if (m_message_callback) {
        m_message_callback(msg->get_payload());
    }
}

void WebSocketManager::onFail(ConnectionHandle hdl) {
    std::cerr << "WebSocket connection failed" << std::endl;
    m_connected = false;
}