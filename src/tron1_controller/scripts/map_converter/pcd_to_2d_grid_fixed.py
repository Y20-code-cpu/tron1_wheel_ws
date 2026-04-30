#!/usr/bin/env python3
"""
3D点云地图转2D栅格地图 (修复版)
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
        self.resolution = resolution
        self.robot_height = robot_height
        self.min_z = min_z
        self.max_z = max_z
        self.obstacle_threshold = obstacle_threshold
        
    def load_pointcloud(self, pcd_path):
        print(f"📂 加载点云: {pcd_path}")
        
        if pcd_path.endswith('.pcd'):
            pcd = o3d.io.read_point_cloud(pcd_path)
        elif pcd_path.endswith('.ply'):
            pcd = o3d.io.read_point_cloud(pcd_path)
        else:
            points = np.loadtxt(pcd_path)
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
        
        points = np.asarray(pcd.points)
        print(f"✅ 加载完成: {len(points)} 个点")
        return points
    
    def filter_points(self, points):
        mask = (points[:, 2] >= self.min_z) & (points[:, 2] <= self.max_z)
        filtered_points = points[mask]
        print(f"📊 过滤后点数: {len(filtered_points)} (范围 {self.min_z}-{self.max_z}m)")
        return filtered_points
    
    def create_grid_map(self, points):
        if len(points) == 0:
            print("⚠️ 没有有效点云")
            return None, None, None
        
        x_min, y_min = np.min(points[:, :2], axis=0)
        x_max, y_max = np.max(points[:, :2], axis=0)
        
        width = int(np.ceil((x_max - x_min) / self.resolution)) + 1
        height = int(np.ceil((y_max - y_min) / self.resolution)) + 1
        
        print(f"🗺️ 地图尺寸: {width} x {height} 栅格")
        print(f"📐 实际范围: X [{x_min:.2f}, {x_max:.2f}] m, Y [{y_min:.2f}, {y_max:.2f}] m")
        
        # 初始化栅格计数
        grid_counts = np.zeros((height, width), dtype=np.int32)
        
        for point in points:
            grid_x = int((point[0] - x_min) / self.resolution)
            grid_y = int((point[1] - y_min) / self.resolution)
            if 0 <= grid_x < width and 0 <= grid_y < height:
                grid_counts[grid_y, grid_x] += 1
        
        # 创建占用地图
        occupancy_map = np.zeros((height, width), dtype=np.uint8)
        obstacle_mask = grid_counts >= self.obstacle_threshold
        occupancy_map[obstacle_mask] = 100
        
        # 简化版膨胀处理
        print("🔄 进行膨胀处理...")
        kernel_size = max(3, int(0.3 / self.resolution))
        
        # 手动膨胀（避免scipy依赖）
        dilated = obstacle_mask.copy()
        for _ in range(kernel_size // 2):
            dilated_temp = dilated.copy()
            for i in range(1, height-1):
                for j in range(1, width-1):
                    if dilated[i, j]:
                        dilated_temp[i-1:i+2, j-1:j+2] = True
            dilated = dilated_temp
        
        occupancy_map[dilated] = 100
        
        # 创建简单的代价地图
        cost_map = occupancy_map.copy()
        
        return occupancy_map, cost_map, (x_min, y_min, x_max, y_max)
    
    def save_map(self, occupancy_map, bounds, output_path):
        base_name = os.path.splitext(output_path)[0]
        pgm_path = base_name + ".pgm"
        yaml_path = base_name + ".yaml"
        
        x_min, y_min, x_max, y_max = bounds
        
        # 保存PGM
        img = Image.fromarray(occupancy_map.astype(np.uint8), mode='L')
        img.save(pgm_path)
        
        # 保存YAML
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
        
        return pgm_path, yaml_path
    
    def convert(self, input_path, output_path, visualize=False):
        print("=" * 50)
        print("🚀 开始转换 3D点云 → 2D栅格地图")
        print("=" * 50)
        
        points = self.load_pointcloud(input_path)
        filtered = self.filter_points(points)
        occupancy_map, cost_map, bounds = self.create_grid_map(filtered)
        
        if occupancy_map is None:
            print("❌ 转换失败")
            return False
        
        self.save_map(occupancy_map, bounds, output_path)
        
        print("=" * 50)
        print("✅ 转换完成!")
        print("=" * 50)
        
        return True

def main():
    parser = argparse.ArgumentParser(description='3D点云转2D栅格地图')
    parser.add_argument('input', help='输入点云文件路径')
    parser.add_argument('output', nargs='?', default='map.yaml', help='输出地图路径')
    parser.add_argument('--resolution', type=float, default=0.05, help='栅格分辨率')
    parser.add_argument('--min-z', type=float, default=0.1, help='障碍物最小高度')
    parser.add_argument('--max-z', type=float, default=1.2, help='障碍物最大高度')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"❌ 输入文件不存在: {args.input}")
        sys.exit(1)
    
    converter = PCD2GridMap(
        resolution=args.resolution,
        min_z=args.min_z,
        max_z=args.max_z
    )
    
    success = converter.convert(args.input, args.output, False)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
