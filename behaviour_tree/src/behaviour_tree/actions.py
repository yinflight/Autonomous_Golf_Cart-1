#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: dexterdmonkey, mpandoko
based on work of: vermillord
Behaviour Tree of Autonomus Golfcart

defining each behaviour trees action in a function
which the output is publishing waypoints
in rostopic : '/wp_planner'
"""

import numpy as np
import rospy
from math import sin, cos
from behaviour_tree.msg import Planner

from behaviour_tree.local_planner.local_planner import LocalPlanner
from behaviour_tree.local_planner.collision_checker import CollisionChecker
from behaviour_tree.local_planner.velocity_planner import VelocityPlanner
from behaviour_tree.local_planner.spiral_generator import SpiralGenerator
import behaviour_tree.condition as cond

# rospy.init_node('action')

def get_start_and_lookahead_index(waypoint, x, y, ld_dist):
    min_idx       = 0
    min_dist      = np.inf
    for i in range(len(waypoint)):
        dist = np.linalg.norm(np.array([
                waypoint[i][0] - x,
                waypoint[i][1] - y]))
        if dist < min_dist:
            min_dist = dist
            min_idx = i

    total_dist = min_dist
    lookahead_idx = min_idx
    for i in range(min_idx + 1, len(waypoint)):
        if total_dist >= ld_dist:
            break
        total_dist += np.linalg.norm(np.array([
                waypoint[i][0] - waypoint[i-1][0],
                waypoint[i][1] - waypoint[i-1][1]]))
        lookahead_idx = i
    
    return min_idx,lookahead_idx

def transform_paths(path, curv, ego_state):
    """
    Transforms the local paths to the global frame
    """
    
    egs = np.copy(ego_state)

    x_transformed = []
    y_transformed = []
    t_transformed = []
    
    for i in range(len(path[0])):
        x_transformed.append(egs[0] + path[0][i]*cos(egs[2]) - \
                                            path[1][i]*sin(egs[2]))
        y_transformed.append(egs[1] + path[0][i]*sin(egs[2]) + \
                                            path[1][i]*cos(egs[2]))
        t_transformed.append(path[2][i] + egs[2])
    
    transformed_path = [x_transformed, y_transformed, t_transformed, curv]
        
    return transformed_path

def follow_leader(curr_state, mission_waypoint, waypoint, a_max):
    freq = rospy.get_param('~freq', 10) # Hz
    ld_dist = rospy.get_param('~ld_dist', 10.0) # m
    
    pub = rospy.Publisher('/wp_planner', Planner, queue_size=1)
    rate = rospy.Rate(freq) # Hz
    msg = Planner()
    msg.header.frame_id = 'local_planner'
    msg.header.seq = 0
    msg.header.stamp = rospy.Time.now()
    last_time = msg.header.stamp.to_sec() - 1./freq

    
    ### Calculate the actual sampling time
    msg.header.stamp = rospy.Time.now()
    delta_t = msg.header.stamp.to_sec() - last_time
    last_time = msg.header.stamp.to_sec()
    
    print("Planning velocity...")
    #Asumsi ketika selisih jarak 5m, kecepatan kendaraan biar 1m/s
    Kgap = 0.2
    
    d_min = 2.4
    l_veh = 2.4
    d_des = max(l_veh*curr_state[3]/5, d_min)
    d_act = cond.leader_distance(waypoint)
    v_cmd = Kgap*(d_act - d_des)
    
    x=[]
    y=[]
    yaw=[]
    v=[]
    curv=[]
    
    #generate velocity
    vp = VelocityPlanner(a_max)
    
    """
    Cara Pertama bikin path, terus di generate waypoint baru, masih error di g_setnya
    """
    # lp = LocalPlanner(waypoint, ld_dist, 1, offset)
    
    # # Generate path
    # ld_idx = lp.get_lookahead_index(curr_state[0],curr_state[1])
    # path = lp.plan_paths([waypoint[ld_idx]])
    # tf_paths = lp.transform_paths(path[0], curr_state)
    # wp = vp.nominal_profile(tf_paths[0], curr_state[3],v_cmd)
    # 
    
    """
    Cara kedua cuma ubah v nya
    """
    # Get current index to lookahead index
    x_ = []
    y_ = []
    yaw_ = []
    curv_ = []
    a,b = get_start_and_lookahead_index(mission_waypoint, curr_state[0],curr_state[1], ld_dist)
    dx = curr_state[0]-mission_waypoint[a][0]
    dy = curr_state[1]-mission_waypoint[a][1]
    
    for i in range (a,b):
        x_.append(mission_waypoint[i][0]+dx)
        y_.append(mission_waypoint[i][1]+dy)
        yaw_.append(mission_waypoint[i][2])
        curv_.append(mission_waypoint[i][4])
    path = [x_,y_,yaw_,curv_]
    wp = vp.nominal_profile(path,curr_state[3],v_cmd)
    
    for i in range(len(wp)):
        x.append(wp[i][0])
        y.append(wp[i][1])
        yaw.append(wp[i][2])
        v.append(wp[i][3])
        curv.append(wp[i][4])
    
    ### Send the message
    # Header
    msg.header.seq += 1
    # Type
    msg.wp_type = 1
    # Waypoints
    msg.x = x
    msg.y = y
    msg.yaw = yaw
    msg.v = v
    msg.curv = curv
    
    # # Plot for debuging
    # idx = [i for i in range(len(v))]
    
    # xwp = []
    # ywp = []
    # for i in range (len(waypoint)):
    #     xwp.append(waypoint[i][0])
    #     ywp.append(waypoint[i][1])
    
    # import matplotlib.pyplot as plt
    # # plt.subplot(1,2,1)
    # plt.plot(x,y,'ro')
    # # plt.plot(xwp,ywp,'go')
    # plt.title('local path generated by local planner')
    # plt.xlabel('x')
    # plt.ylabel('y')
    # plt.show()
    
    # # plt.subplot(1,2,2)
    # plt.plot(idx,v,'b')
    # plt.title('velocity planeer vs index')
    # plt.xlabel('i')
    # plt.ylabel('v')
    # plt.show()
    
    # # Publish the message
    pub.publish(msg)
    
def track_speed(curr_state, mission_waypoint, v_ts, a_max):
    freq = rospy.get_param('~freq', 10) # Hz
    ld_dist = rospy.get_param('~ld_dist', 10.0) # m
    
    pub = rospy.Publisher('/wp_planner', Planner, queue_size=1)
    rate = rospy.Rate(freq) # Hz
    msg = Planner()
    msg.header.frame_id = 'local_planner'
    msg.header.seq = 0
    msg.header.stamp = rospy.Time.now()
    last_time = msg.header.stamp.to_sec() - 1./freq

    print("State estimation received!")
    
    ### Calculate the actual sampling time
    msg.header.stamp = rospy.Time.now()
    delta_t = msg.header.stamp.to_sec() - last_time
    last_time = msg.header.stamp.to_sec()
    
    print("Planning velocity...")
    v_cmd = v_ts

    x=[]
    y=[]
    yaw=[]
    v=[]
    curv=[]
    
    #generate velocity
    vp = VelocityPlanner(a_max)
    
    """
    Cara Pertama bikin path, terus di generate waypoint baru, masih error di g_setnya
    """
    # lp = LocalPlanner(waypoint, ld_dist, 1, offset)
    
    # # Generate path
    # ld_idx = lp.get_lookahead_index(curr_state[0],curr_state[1])
    # path = lp.plan_paths([waypoint[ld_idx]])
    # tf_paths = lp.transform_paths(path[0], curr_state)
    # wp = vp.nominal_profile(tf_paths[0], curr_state[3],v_cmd)
    # 
    
    """
    Cara kedua cuma ubah v nya
    Batasan dan asumsi: Mobil bergerak lurus
    Saran: Mobil tidak bisa mengikuti path melengkung
    """
    # Get current index to lookahead index
    x_ = []
    y_ = []
    yaw_ = []
    curv_ = []
    a,b = get_start_and_lookahead_index(mission_waypoint, curr_state[0],curr_state[1], ld_dist)
    dx = curr_state[0]-mission_waypoint[a][0]
    dy = curr_state[1]-mission_waypoint[a][1]
    
    for i in range (a,b):
        x_.append(mission_waypoint[i][0]+dx)
        y_.append(mission_waypoint[i][1]+dy)
        yaw_.append(mission_waypoint[i][2])
        curv_.append(mission_waypoint[i][4])
    path = [x_,y_,yaw_,curv_]
    wp = vp.nominal_profile(path,curr_state[3],v_cmd)
    
    for i in range(len(wp)):
        x.append(wp[i][0])
        y.append(wp[i][1])
        yaw.append(wp[i][2])
        v.append(v_cmd)
        curv.append(wp[i][4])
    
    ### Send the message
    # Header
    msg.header.seq += 1
    # Type
    msg.wp_type = 1
    # Waypoints
    msg.x = x
    msg.y = y
    msg.yaw = yaw
    msg.v = v
    msg.curv = curv
    
    # # Plot for debuging
    # idx = [i for i in range(len(v))]
    
    # xwp = []
    # ywp = []
    # for i in range (len(waypoint)):
    #     xwp.append(waypoint[i][0])
    #     ywp.append(waypoint[i][1])
    
    # import matplotlib.pyplot as plt
    # # plt.subplot(1,2,1)
    # plt.plot(x,y,'ro')
    # # plt.plot(xwp,ywp,'go')
    # plt.title('local path generated by local planner')
    # plt.xlabel('x')
    # plt.ylabel('y')
    # plt.show()
    
    # # plt.subplot(1,2,2)
    # plt.plot(idx,v,'b')
    # plt.title('velocity planeer vs index')
    # plt.xlabel('i')
    # plt.ylabel('v')
    # plt.show()
    
    # Publish the message
    pub.publish(msg)
    
def decelerate_to_stop(curr_state, xf,yf,yawf, a_max):
    freq = rospy.get_param('~freq', 10) # Hz
    ld_dist = rospy.get_param('~ld_dist', 10.0) # m
    
    pub = rospy.Publisher('/wp_planner', Planner, queue_size=1)
    rate = rospy.Rate(freq) # Hz
    msg = Planner()
    msg.header.frame_id = 'local_planner'
    msg.header.seq = 0
    msg.header.stamp = rospy.Time.now()
    last_time = msg.header.stamp.to_sec() - 1./freq
    
    ### Calculate the actual sampling time
    msg.header.stamp = rospy.Time.now()
    delta_t = msg.header.stamp.to_sec() - last_time
    last_time = msg.header.stamp.to_sec()
    
    print("Planning velocity...")
    v_cmd = 0
    
    x=[]
    y=[]
    yaw=[]
    v=[]
    curv=[]
    
    #generate velocity
    vp = VelocityPlanner(a_max)
    path_generator = SpiralGenerator()
    path = path_generator.optimize_spiral(
            xf-curr_state[0],
            yf-curr_state[1],
            yawf-curr_state[2]
        )
    curv = path_generator.get_curvature()
    tf_path = transform_paths(path,curv,curr_state)

    wp = vp.nominal_profile(tf_path,curr_state[3],v_cmd)
    
    for i in range(len(wp)):
        x.append(wp[i][0])
        y.append(wp[i][1])
        yaw.append(wp[i][2])
        v.append(wp[i][3])
        curv.append(wp[i][4])
    
    ### Send the message
    # Header
    msg.header.seq += 1
    # Type
    msg.wp_type = 1
    # Waypoints
    msg.x = x
    msg.y = y
    msg.yaw = yaw
    msg.v = v
    msg.curv = curv
    
    # # Plot for debuging
    # idx = [i for i in range(len(v))]
    
    # xwp = []
    # ywp = []
    # for i in range (len(waypoint)):
    #     xwp.append(waypoint[i][0])
    #     ywp.append(waypoint[i][1])
    
    # import matplotlib.pyplot as plt
    # # plt.subplot(1,2,1)
    # plt.plot(x,y,'ro')
    # # plt.plot(xwp,ywp,'go')
    # plt.title('local path generated by local planner')
    # plt.xlabel('x')
    # plt.ylabel('y')
    # plt.show()
    
    # # plt.subplot(1,2,2)
    # plt.plot(idx,v,'b')
    # plt.title('velocity planeer vs index')
    # plt.xlabel('i')
    # plt.ylabel('v')
    # plt.show()
    
    # Publish the message
    pub.publish(msg)

def switch_lane(curr_state,mission_waypoints,pred_time,a_max):
    freq = rospy.get_param('~freq', 10) # Hz
    ld_dist = rospy.get_param('~ld_dist', 10.0) # m
    n_offset = rospy.get_param('~n_offset', 5) # m
    offset = rospy.get_param('~offset', 3) # m
    c_location = rospy.get_param('~c_location', [-1, 1, 3]) # m
    c_rad = rospy.get_param('~c_rad', [1.5, 1.5, 1.5]) # m
    d_weight = rospy.get_param('~d_weight', 0.5)
    
    # Create local planner classes
    lp = LocalPlanner(mission_waypoints, ld_dist, n_offset, offset)
    cc = CollisionChecker(c_location, c_rad, d_weight)
    vp = VelocityPlanner(a_max)
    
    # Create publisher and subscriber
    # rospy.Subscriber('/ukf_states', ukf_states, state_callback)
    pub = rospy.Publisher('/wp_planner', Planner, queue_size=1)
    rate = rospy.Rate(freq) # Hz

    # Wait until we get the actual state
    # print("Waiting for state estimation...")
    # RUN = False
    # while not RUN:
    #     time.sleep(0.02) # 20 ms
    #     pass

    msg = Planner()
    msg.header.frame_id = 'local_planner'
    msg.header.seq = 0
    msg.header.stamp = rospy.Time.now()
    last_time = msg.header.stamp.to_sec() - 1./freq

    # Set waypoints type (0: global, 1: local)
    # wp_type = 0
    
    print("State estimation received!")
    print("Planning local paths...")

    ### Calculate the actual sampling time
    msg.header.stamp = rospy.Time.now()
    delta_t = msg.header.stamp.to_sec() - last_time
    last_time = msg.header.stamp.to_sec()
    
    #Local Planner
    print('Generating feasible paths...')
    
    # Get lookahead index
    ld_idx = lp.get_lookahead_index(curr_state[0], curr_state[1])
    print('Lookahead yaw: ', mission_waypoints[ld_idx][2])
    
    # Get offset goal states, pada acuan lokal
    g_set = lp.get_goal_state_set(mission_waypoints[ld_idx], curr_state)
    
    # Plan paths, dengan acuan local ke gset acuan local
    path_generated = lp.plan_paths(g_set)
    
    print('Path generated!')
    print('Status:', path_generated[1])

    # Assign object points to array
    obstacles = cond.obstacles_classifier()
    obj_ = []
    x_ = []
    z_ = []
    for obstacle in obstacles:
        x, z = cond.occupancy_grid(obstacle,pred_time)
        x_ = x_+x
        z_ = z_+z
    for i in range (len(x_)):
        obj_.append([x_[i],z_[i]])
    obj_ = np.array(obj_)  
    
# =============================================================================
#     # Plot data for debugging
#     plt.clf()
#     plt.scatter(0, 0, color='k', label='start')
#     for goal in g_set:
#         plt.scatter(goal[0], goal[1], color='b')
#     for path in path_generated[0]:
#         plt.plot(path[0], path[1], color='g')
#     plt.xlabel('x(m)')
#     plt.ylabel('y(m)')
#     plt.legend()
#     plt.show()
# =============================================================================
    
    # Collision Check
    coll = cc.collision_check(path_generated[0], obj_)
    print('select:',coll)
    bp = cc.path_selection(path_generated[0], coll, g_set[n_offset//2])
    
    # Declare variables
    x = []
    y = []
    yaw = []
    v = []
    curv = []

    # Set waypoints type
    wp_type = 1
    
    # Transform paths, ke acuan global
    tf_paths = lp.transform_paths(path_generated[0], curr_state)
    
    # Generate waypoints with speed and curvature
    # Format [x, y, t, v, curv]
    best_wp = vp.nominal_profile(tf_paths[bp], curr_state[-1], g_set[bp][-1])
    # print("wp_generated: ",best_wp)

    # Add starting waypoints
    wp_0 = curr_state
    wp_0.append(0.0)
    wp_0 = [(best_wp[0][0] + wp_0[0])/2, (best_wp[0][1] + wp_0[1])/2, (best_wp[0][2] + wp_0[2])/2,
            (best_wp[0][3] + wp_0[3])/2, (best_wp[0][4] + wp_0[4])/2]
    #best_wp.insert(0, wp_0)
    
    # Convert waypoints to message format
    for i in range(len(best_wp)):
        x.append(best_wp[i][0])
        y.append(best_wp[i][1])
        yaw.append(best_wp[i][2])
        v.append(best_wp[i][3])
        curv.append(best_wp[i][4])
    
    print('Local waypoints used:', bp)

    ### Send the message
    # Header
    msg.header.seq += 1
    # Type
    msg.wp_type = wp_type
    # Waypoints
    msg.x = x
    msg.y = y
    msg.yaw = yaw
    msg.v = v
    msg.curv = curv
    
    # Plot for debuging
    idx = [i for i in range(len(v))]
    
    # xwp = []
    # ywp = []
    # for i in range (len(waypoints)):
    #     xwp.append(waypoints[i][0])
    #     ywp.append(waypoints[i][1])
    
    # import matplotlib.pyplot as plt
    # plt.subplot(1,2,1)
    # plt.plot(x,y,'ro')
    # # plt.plot(xwp,ywp,'go')
    # plt.title('local path generated by local planner')
    # plt.xlabel('x')
    # plt.ylabel('y')
    # plt.show()
    
    # # plt.subplot(1,2,2)
    # plt.plot(idx,v,'b')
    # plt.title('velocity planeer vs index')
    # plt.xlabel('i')
    # plt.ylabel('v')
    # plt.show()
    
    # Publish the message
    pub.publish(msg)

    while(True):
        obstacles = cond.obstacles_classifier()
        obj_ = []
        x_ = []
        z_ = []
        for obstacle in obstacles:
            x, z = cond.occupancy_grid(obstacle,pred_time)
            x_ = x_+x
            z_ = z_+z
            
        # Ini rumus buat transformasi objek ketika vehicle mengahadap serong
        # xx = z[i]*(np.sec(curr_state[2])-np.tan(curr_state[2])*np.sin(curr_state[2])) + x[i]*np.sin(curr_state[2])
        # yy = z[i]*np.sin(curr_state[2])-x[i]*np.cos(curr_state[2])
            
        # Collision Check
        coll = cc.collision_check([path_generated[0][bp]], obj_)
        print("Vehicle is switching lane, no collision detected")
        if not coll:
            print("STATUS: Collision detected, switching lane end")
            break
        print("STATUS: Vehicle has successfully switched lane")