#!/usr/bin/env python3
"""
3D点云地图转2D栅格地图
用法: python3 pcd_to_2d_grid.py <input.pcd> <output.yaml>
"""

import open3d as o3d
import numpy as np
import yaml
from PIL import Image
import sys
import os
import argparse

class PCD2GridMap:
    def __init__(self, resolution=0.05, robot_height=0.8, 
                 min_z=0.1, max_z=1.2, obstacle_threshold=5):
        """
        参数:
            resolution: 栅格分辨率 (米/像素)
            robot_height: 机器人高度 (米)
            min_z: 障碍物最小高度 (米)
            max_z: 障碍物最大高度 (米)
            obstacle_threshold: 一个格子内最少点数才视为障碍物
        """
        self.resolution = resolution
        self.robot_height = robot_height
        self.min_z = min_z
        self.max_z = max_z
        self.obstacle_threshold = obstacle_threshold
        
    def load_pointcloud(self, pcd_path):
        """加载点云文件"""
        print(f"📂 加载点云: {pcd_path}")
        
        if pcd_path.endswith('.pcd'):
            pcd = o3d.io.read_point_cloud(pcd_path)
        elif pcd_path.endswith('.ply'):
            pcd = o3d.io.read_point_cloud(pcd_path)
        else:
            # 尝试读取文本格式
            points = np.loadtxt(pcd_path)
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
        
        points = np.asarray(pcd.points)
        print(f"✅ 加载完成: {len(points)} 个点")
        return points
    
    def filter_points(self, points):
        """过滤点云：保留高度在机器人范围内的点"""
        # 筛选高度范围内的点
        mask = (points[:, 2] >= self.min_z) & (points[:, 2] <= self.max_z)
        filtered_points = points[mask]
        print(f"📊 过滤后点数: {len(filtered_points)} (范围 {self.min_z}-{self.max_z}m)")
        return filtered_points
    
    def create_grid_map(self, points):
        """创建栅格地图"""
        if len(points) == 0:
            print("⚠️ 没有有效点云")
            return None, None, None
        
        # 获取点云边界
        x_min, y_min = np.min(points[:, :2], axis=0)
        x_max, y_max = np.max(points[:, :2], axis=0)
        
        # 计算栅格尺寸
        width = int(np.ceil((x_max - x_min) / self.resolution)) + 1
        height = int(np.ceil((y_max - y_min) / self.resolution)) + 1
        
        print(f"🗺️ 地图尺寸: {width} x {height} 栅格")
        print(f"📐 实际范围: X [{x_min:.2f}, {x_max:.2f}] m, Y [{y_min:.2f}, {y_max:.2f}] m")
        
        # 初始化栅格计数
        grid_counts = np.zeros((height, width), dtype=np.int32)
        
        # 将点映射到栅格
        for point in points:
            grid_x = int((point[0] - x_min) / self.resolution)
            grid_y = int((point[1] - y_min) / self.resolution)
            grid_counts[grid_y, grid_x] += 1
        
        # 创建障碍物地图 (0: 空闲, 100: 占用)
        occupancy_map = np.zeros((height, width), dtype=np.uint8)
        
        # 标记障碍物（点数超过阈值）
        obstacle_mask = grid_counts >= self.obstacle_threshold
        occupancy_map[obstacle_mask] = 100
        
        # 膨胀处理（扩大障碍物边界，考虑机器人半径）
        # 简单膨胀：对每个障碍物，周围膨胀
        from scipy.ndimage import binary_dilation
        import scipy.ndimage as ndimage
        
        # 创建结构元素（机器人半径约0.3m）
        kernel_size = int(0.3 / self.resolution)  # 3个栅格
        kernel = np.ones((kernel_size, kernel_size))
        
        # 膨胀
        obstacles = occupancy_map == 100
        dilated = binary_dilation(obstacles, structure=kernel)
        occupancy_map[dilated] = 100
        
        # 创建代价地图（0-100，数字越大越危险）
        cost_map = np.zeros((height, width), dtype=np.uint8)
        cost_map[occupancy_map == 100] = 100
        
        # 可选：创建边界区域（膨胀边缘）
        # 为障碍物添加渐变代价
        distance = ndimage.distance_transform_edt(~dilated)
        max_dist = 0.5 / self.resolution  # 0.5米内逐渐衰减
        near_obstacle = (distance < max_dist) & (distance > 0)
        cost_map[near_obstacle] = (1 - distance / max_dist) * 80 + 20
        
        return occupancy_map, cost_map, (x_min, y_min, x_max, y_max)
    
    def save_map(self, occupancy_map, bounds, output_path):
        """保存地图为PGM+YAML格式（ROS兼容）"""
        # 创建输出路径
        base_name = os.path.splitext(output_path)[0]
        pgm_path = base_name + ".pgm"
        yaml_path = base_name + ".yaml"
        
        x_min, y_min, x_max, y_max = bounds
        
        # 保存PGM图像
        img = Image.fromarray(occupancy_map.astype(np.uint8), mode='L')
        img.save(pgm_path)
        
        # 创建YAML配置
        map_metadata = {
            'image': os.path.basename(pgm_path),
            'resolution': self.resolution,
            'origin': [x_min, y_min, 0.0],
            'negate': 0,
            'occupied_thresh': 0.65,
            'free_thresh': 0.25
        }
        
        with open(yaml_path, 'w') as f:
            yaml.dump(map_metadata, f, default_flow_style=False)
        
        print(f"✅ 地图已保存:")
        print(f"   PGM: {pgm_path}")
        print(f"   YAML: {yaml_path}")
        
        # 同时保存costmap（可选）
        return pgm_path, yaml_path
    
    def visualize(self, points, occupancy_map):
        """可视化点云和栅格地图"""
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        
        # 点云俯视图
        ax = axes[0]
        ax.scatter(points[:, 0], points[:, 1], s=0.1, c=points[:, 2], cmap='viridis')
        ax.set_title('点云俯视图')
        ax.set_xlabel('X (m)')
        ax.set_ylabel('Y (m)')
        ax.set_aspect('equal')
        
        # 栅格地图
        ax = axes[1]
        ax.imshow(occupancy_map, cmap='gray', origin='lower')
        ax.set_title('2D栅格地图 (白色=障碍物)')
        ax.set_xlabel('栅格 X')
        ax.set_ylabel('栅格 Y')
        
        plt.tight_layout()
        plt.show()
    
    def convert(self, input_path, output_path, visualize=False):
        """完整的转换流程"""
        print("=" * 50)
        print("🚀 开始转换 3D点云 → 2D栅格地图")
        print("=" * 50)
        
        # 加载点云
        points = self.load_pointcloud(input_path)
        
        # 过滤点云
        filtered = self.filter_points(points)
        
        # 创建栅格地图
        occupancy_map, cost_map, bounds = self.create_grid_map(filtered)
        
        if occupancy_map is None:
            print("❌ 转换失败")
            return False
        
        # 保存地图
        self.save_map(occupancy_map, bounds, output_path)
        
        # 可选：保存costmap
        cost_path = output_path.replace('.yaml', '_costmap.npy')
        np.save(cost_path, cost_map)
        print(f"   Costmap: {cost_path}")
        
        # 可视化
        if visualize:
            self.visualize(filtered, occupancy_map)
        
        print("=" * 50)
        print("✅ 转换完成!")
        print("=" * 50)
        
        return True

def main():
    parser = argparse.ArgumentParser(description='3D点云转2D栅格地图')
    parser.add_argument('input', help='输入点云文件路径 (.pcd, .ply, .txt)')
    parser.add_argument('output', nargs='?', default='map.yaml', 
                        help='输出地图路径 (默认: map.yaml)')
    parser.add_argument('--resolution', type=float, default=0.05,
                        help='栅格分辨率 (米/像素, 默认: 0.05)')
    parser.add_argument('--robot-height', type=float, default=0.8,
                        help='机器人高度 (米, 默认: 0.8)')
    parser.add_argument('--min-z', type=float, default=0.1,
                        help='障碍物最小高度 (米, 默认: 0.1)')
    parser.add_argument('--max-z', type=float, default=1.2,
                        help='障碍物最大高度 (米, 默认: 1.2)')
    parser.add_argument('--visualize', action='store_true',
                        help='显示可视化')
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"❌ 输入文件不存在: {args.input}")
        sys.exit(1)
    
    # 创建转换器
    converter = PCD2GridMap(
        resolution=args.resolution,
        robot_height=args.robot_height,
        min_z=args.min_z,
        max_z=args.max_z
    )
    
    # 执行转换
    success = converter.convert(args.input, args.output, args.visualize)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()