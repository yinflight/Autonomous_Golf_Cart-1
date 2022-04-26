#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Created on Apr 22, 2022
@author: dexterdmonkey

Behaviour Tree of Autonomus Golfcart
"""


"""
.. argparse::
   :module: py_trees.demos.trees
   :func: command_line_argument_parser
   :prog: py-trees-demo-trees

.. graphviz:: dot/demo-trees.dot

.. image:: images/trees.gif

"""
##############################################################################
# Imports
##############################################################################

from ast import arg
from asyncio import current_task
from glob import glob
from io import SEEK_CUR
from pickle import GLOBAL
from tkinter import E, N
from turtle import pos
# from flask import copy_current_request_context

import os
import rospkg
import py_trees
import argparse
import sys
import time
import rospy
import numpy as np
import py_trees.console as console

#import dari local_planner
from behaviour_tree.local_planner.collision_checker import CollisionChecker
from behaviour_tree.local_planner.local_planner import LocalPlanner
from behaviour_tree.local_planner.velocity_planner import VelocityPlanner

from multiprocessing.pool import RUN
from persepsi.msg import obj_points
from behaviour_tree.msg import Planner, ukf_states
from rospy.numpy_msg import numpy_msg
from rospy_tutorials.msg import Floats


##############################################################################
# Setup Variables
##############################################################################

v_threshold = rospy.get_param('~freq', 5) # Hz
waypoints_path = rospy.get_param('~waypoints_path', 'ica_2.npy')
# waypoints_path = os.path.abspath(sys.path[0] + '/../../pkg_ta/src/waypoints/waypoints/' + waypoints_path)
c_location = rospy.get_param('~c_location', [-1.0, 1.0, 3.0]) # m
c_rad = rospy.get_param('~c_rad', [1.5, 1.5, 1.5]) # m
d_weight = rospy.get_param('~d_weight', 0.5)
prediction_time = rospy.get_param('~pred_time',2) #s

# waypoints = np.load(waypoints_path) + [0, 0, -np.pi/5, 0, 0]

# Set callback data and variables
planner = {
    'wp_type': 0,
    'x': [0., 0.],
    'y': [0., 0.],
    'yaw': [0., 0.],
    'v': [0., 0.],
    'curv': [0., 0.]
}
obj = {
    'obj_len': [1, 1],
    'obj_x': [1e5, 1e5],
    'obj_y': [1e5, 1e5],
    'obj_z': [1e5, 1e5],
    'xc': [1e5, 1e5],
    'zc': [1e5, 1e5],
    'vxc': [1e5, 1e5],
    'vzc': [1e5, 1e5],
}
state = {
    'x':0.,
    'y':0.,
    'yaw':0.,
    'v':0.,
}
RUN = False

def state_callback(msg_nav):
    global state
    global RUN
    
    state['x'] = msg_nav.x
    state['y'] = msg_nav.y
    state['v'] = np.sqrt(msg_nav.vx**2 + msg_nav.vy**2)
    state['yaw'] = msg_nav.yaw_est
    
    RUN = True
     
def perception_callback(data):
    global obj
    
    obj['obj_len'] = data.obj_len
    obj['obj_x'] = data.obj_x
    obj['obj_y'] = data.obj_y
    obj['obj_z'] = data.obj_z
    obj['xc'] = data.xc
    obj['zc'] = data.zc
    obj['vxc'] = data.vxc
    obj['vzc'] = data.vzc
    
def planner_callback(planner_msg):
    global planner
    
    planner['wp_type'] = planner_msg.wp_type
    planner['x'] = planner_msg.x
    planner['y'] = planner_msg.y
    planner['yaw'] = planner_msg.yaw
    planner['v'] = planner_msg.v
    planner['curv'] = planner_msg.curv

def pose():
    global state
    
    curr_state = [state['x'], state['y'], state['yaw']-np.pi/5, state['v']]
    return curr_state

def waypoint():
    global waypoint
    
    curr_waypoint = [planner['x'],planner['y'],planner['yaw'],planner['v'],planner['curv']]
    if len(curr_waypoint):
        curr_waypoint = np.load(os.path.abspath(__file__+"/../waypoints/lurus_ica_2.npy"))
        
    return curr_waypoint

#Mereturn jarak kendaraan saat ini dengan titik tujuan
def d_rem(waypoint):
    global state
    
    #State mobil sekarang
    x1 = state['x']
    y1 = state['y']
    
    #Titik akhir tujuan
    x2 = waypoint[-1][0]
    y2 = waypoint[-1][1]
    d_remain = np.sqrt((x2-x1)**2+(y2-y1)**2) #meter
    return d_remain

#Memisahkan data object points untuk setiap object
def obstacles_classifier():
    global obj
    rospy.Subscriber('/object_points', obj_points, perception_callback)
    obs = []
    a = 0
    for i in range (len(obj['obj_len'])):
        b = int(a + obj['obj_len'][i])
        obj_row = {
            'id': i,
            'obj_x': obj['obj_x'][a:b],
            'obj_y': obj['obj_y'][a:b],
            'obj_z': obj['obj_z'][a:b],
            'xc': obj['xc'][i],
            'zc': obj['zc'][i],
            'vxc': obj['vxc'][i],
            'vzc': obj['vzc'][i],
        }
        obs.append(obj_row)
        a = b
    return obs

# Memeriksa apakah ada objek. dimana:
# - waypoint = [x,y,yaw,curve,v]
# - obj_ adalah matriks objek dalam occupancy grid

def leader_selection(waypoint):
    obstacles = obstacles_classifier
    
    #Colllision Check Class
    cc = CollisionChecker(c_location, c_rad, d_weight)
    obstacles = obstacles_classifier()
    obj_coll_id = []
    obj_coll_zc = []
    obc_coll_vzc = []
    for obstacle in obstacles:
        x = obstacle['obj_x']
        z = obstacle['obj_z']
        
        # Assign object points to array
        obj_ = np.zeros([len(x), 2])
        for i in range(len(x)):
            obj_[i] = [z[i], x[i]]
        coll = cc.collision_check([waypoint], obj_)
        if coll[0]:
            # obj_coll_id.append(obstacle["id"])
            # obj_coll_zc.append(obstacle["zc"])
            if (not len(obj_coll_zc)) or obj_coll_zc > [obstacle['zc']]:
                obj_coll_id = [obstacle['id']]
                obj_coll_zc = [obstacle['zc']]
                obc_coll_vzc = [obstacle['vzc']]
    return [obj_coll_id, obc_coll_vzc]

def is_leader_ex(waypoint):
    id = leader_selection(waypoint)[0]
    if (not len(id)):
        return True
    else:
        return False
    
def leader_velocity(waypoint):
    vzc = leader_selection(waypoint)[1]
    return vzc

# Occupancy Grid filler for one object,
# with additional grid for object moving based on predicted time.
def occupancy_grid(obstacle, pred_time):
    obj_x = obstacle['obj_x']
    obj_z = obstacle['obj_z']
    vxc = obstacle['vxc']
    vzc = obstacle['vzc']
    for i in range(pred_time-1):
        for j in range(len(obj_x)):
            obj_x.append(obj_x[j] + vxc*(i+1))
            obj_z.append(obj_z[j] + vzc*(i+1))
    return obj_z, obj_x


# checking every path generated
# is there free collision path
# The output is either True or None
def possible_path(waypoints):
    ld_dist = rospy.get_param('~ld_dist', 5.0) # m
    n_offset = rospy.get_param('~n_offset', 5) # m
    offset = rospy.get_param('~offset', 0.5) # m
    pred_time = rospy.get_param('~pred_time', 2) #s
    a_max = rospy.get_param('~a_max', 0.005) # m/s^2
    
    lp = LocalPlanner(waypoints, ld_dist, n_offset, offset)
    cc = CollisionChecker(c_location, c_rad, d_weight)
    vp = VelocityPlanner(a_max)
    
    curr_state = pose

    print("State estimation received!")
    print("Planning local paths...")
    ### Generate feasible paths for collision checker
    print('Generating feasible paths...')
    
    # Format [x, y, t, v]
    curr_state = [state['x'], state['y'], state['yaw']-np.pi/5, state['v']]
    print('Current yaw: ', curr_state[2])
    print('Current x, y: ', curr_state[:2])
    
    # Set waypoints type (0: global, 1: local)
    wp_type = 0
    
    # Get lookahead index
    ld_idx = lp.get_lookahead_index(curr_state[0], curr_state[1])
    print('Lookahead yaw: ', waypoints[ld_idx][2])

    
    # Get offset goal states
    g_set = lp.get_goal_state_set(waypoints[ld_idx], waypoints, curr_state)
    
    # Plan paths
    path_generated = lp.plan_paths(g_set)
    
    print('Path generated!')
    print('Status:', path_generated[1])
    
    obstacles = obstacles_classifier() 
    # Assign object points to array
    obj_ = np.zeros([len(x), 2])
    for i in range (len(obstacles)):
        z, x = occupancy_grid(obstacles[i], pred_time)
        obj_[i] = [z[i], x[i]]
    
    # Collision check for every path generated
    coll = cc.collision_check(path_generated[0], obj_)
        # Selecting the best path
    for i in range (len(coll)):
        if coll[i] == True:
            return True
        else:
            False

def condition():
    # In ROS, nodes are uniquely named. If two nodes with the same
    # name are launched, the previous one is kicked off. The
    # anonymous=True flag means that rospy will choose a unique
    # name for our 'listener' node so that multiple listeners can
    # run simultaneously.
    rospy.init_node('condition', anonymous=True)
    rospy.Subscriber('/object_points', obj_points, perception_callback)
    rospy.Subscriber('/ukf_states', ukf_states, state_callback)
    rospy.Subscriber('/wp_planner', Planner, planner_callback)
    # spin() simply keeps python from exiting until this node is stopped
    rospy.spin()


if __name__ == '__main__':
    condition()