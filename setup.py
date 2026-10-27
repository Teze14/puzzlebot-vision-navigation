from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'puzzlebot_follower'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Jesus',
    description='Reto de seguimiento de linea Puzzlebot',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'line_detector  = puzzlebot_follower.line_detector:main',
            'final_detector = puzzlebot_follower.line_colors_detector:main',
            'cnn_detector   = puzzlebot_follower.cnn_detector:main',
            'decision_logic = puzzlebot_follower.decision_logic:main',
        ],
    },
)
