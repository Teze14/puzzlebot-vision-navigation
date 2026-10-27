import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('puzzlebot_follower'),
        'config',
        'params.yaml'
    )

    line_detector_node = Node(
        package='puzzlebot_follower',
        executable='final_detector',
        name='line_follower_vision'
    )

    cnn_detector_node = Node(
        package='puzzlebot_follower',
        executable='cnn_detector',
        name='cnn_detector',
        parameters=[config]
    )

    decision_node = Node(
        package='puzzlebot_follower',
        executable='decision_logic',
        name='puzzlebot_decision_logic',
        parameters=[config]
    )

    return LaunchDescription([
        line_detector_node,
        cnn_detector_node,
        decision_node,
    ])
