cmake_minimum_required(VERSION 3.0.2)
project(tron1_controller)

find_package(catkin REQUIRED COMPONENTS
  roscpp
  rospy
  std_msgs
  geometry_msgs
  sensor_msgs
)

catkin_package()

include_directories(
  include
  ${catkin_INCLUDE_DIRS}
)

# 添加WebSocket客户端库
add_library(websocket_client src/websocket_client.cpp)
target_link_libraries(websocket_client ${catkin_LIBRARIES})

# 添加主节点可执行文件
add_executable(tron1_controller_node src/tron1_controller_node.cpp)
target_link_libraries(tron1_controller_node 
  websocket_client
  ${catkin_LIBRARIES}
)

# ===== 修正后的安装部分 =====
install(TARGETS tron1_controller_node websocket_client
  ARCHIVE DESTINATION ${CATKIN_PACKAGE_LIB_DESTINATION}
  LIBRARY DESTINATION ${CATKIN_PACKAGE_LIB_DESTINATION}
  RUNTIME DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch
)

install(PROGRAMS scripts/keyboard_control.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
  OPTIONAL
)

# 安装头文件
install(DIRECTORY include/${PROJECT_NAME}/
  DESTINATION ${CATKIN_PACKAGE_INCLUDE_DESTINATION}
  FILES_MATCHING PATTERN "*.h"
)