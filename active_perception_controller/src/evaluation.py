#!/usr/bin/env python
from geometry_msgs.msg import Point32
from geometry_msgs.msg import PointStamped
from geometry_msgs.msg import Pose
from geometry_msgs.msg import PoseStamped
from geometry_msgs.msg import PoseWithCovariance
from geometry_msgs.msg import PoseWithCovarianceStamped
from math import *
from nav_msgs.srv import GetMap
from nav_msgs.msg import Path,OccupancyGrid
from active_perception_controller.srv import ActivePerceptionPlan, ActivePerceptionPlanResponse
import tf
import pdb
import rospy
import roslib
from rospy.numpy_msg import numpy_msg
from sensor_msgs.msg import PointCloud, ChannelFloat32
from sklearn.neighbors import NearestNeighbors
import time
import threading
import numpy as np
import scipy as sp
import scipy.ndimage
from costlib import Cost_Manager
from StringIO import StringIO
from geometry_msgs.msg._PoseStamped import PoseStamped
from visualization_msgs.msg import Marker,MarkerArray
import matplotlib.pyplot as plt
import itertools
from helper_functions import pixel_to_point
import cProfile, pstats, StringIO
from scipy.ndimage.filters import gaussian_filter
from copy import deepcopy
import rosbag
from active_perception_controller.srv import positionChange,ppl_positionChange
import os
from motion_planner import path_to_pose,MotionPlanner
import helper_functions as fn
from active_perception_controller.msg import Person,PersonArray
from mmp import example
from experiment_loading import experiment_load2,experiment_load_sevilla

CURRENT = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.split(CURRENT)[0]


class Evaluator(object):
    def __init__(self):
        self.exp_name = rospy.get_param("~experiment_name", "posq_test_exp3")
        self.session_name = rospy.get_param("~session_name", "posq_learn_small2")
        self.real_data = rospy.get_param("~real_data", True)
        self.no_of_runs = rospy.get_param( "number_of_runs",2)
        self.filepath = PARENT
        print PARENT,CURRENT
        self.directory = self.filepath+"/data/"+self.exp_name
        self.results_dir = self.filepath+"/results/"+self.session_name+"/"
        #self.real_data_eval()
        self.experiment_data = experiment_load2(self.directory)
        self.gt_weights = fn.pickle_loader(self.directory+"/weights.pkl")
        self.results = [];
        # print self.results_dir
        # print "gothere"
        for i in range(self.no_of_runs):
            self.results.append(fn.pickle_loader(self.results_dir+"results_"+str(i+1)+".pkl"))
        # self.results = self.results[:3]
        # self.no_of_runs=2
        self.plots()
        # self.planner = MotionPlanner()
        # self.costlib = self.planner.cost_manager
        # self.ppl_pub =  rospy.Publisher("person_poses",PersonArray,queue_size = 10)
        # self.expert_path_pub = rospy.Publisher("expert_path",Path,queue_size = 1)
        # self.initial_paths_pub = rospy.Publisher("initial_weights_path",Path,queue_size = 1)
        # self.final_paths_pub = rospy.Publisher("final_weights_path",Path,queue_size = 1)
        # self.point_sub = rospy.Subscriber("clicked_point",PointStamped,self.point_cb)
        # self.astar_03_path_pub = rospy.Publisher("astar03_path",Path,queue_size = 1)
        # self.astar_08_path_pub = rospy.Publisher("astar08_path",Path,queue_size = 1)
        # self.crlt_path_pub = rospy.Publisher("crlt_path",Path,queue_size = 1)
        self.visualization_counter = 0

    def real_data_eval(self):
        self.results = []
        self.experiment_data = experiment_load_sevilla(self.directory)
        for i in range(self.no_of_runs):
             self.results.append(fn.pickle_loader(self.results_dir+"results_"+str(i+1)+".pkl"))
        self.planner = MotionPlanner()
        self.costlib = self.planner.cost_manager
        self.ppl_pub =  rospy.Publisher("person_poses",PersonArray,queue_size = 1)
        self.expert_path_pub = rospy.Publisher("expert_path",Path,queue_size = 1)
        self.initial_paths_pub = rospy.Publisher("initial_weights_path",Path,queue_size = 1)
        self.final_paths_pub = rospy.Publisher("final_weights_path",Path,queue_size = 1)
        self.point_sub = rospy.Subscriber("clicked_point",PointStamped,self.point_cb_real)
        # self.crlt_path_pub = rospy.Publisher("crlt_path",Path,queue_size = 1)
    def get_multiple_runs(self,method):
        time_taken = []
        for i in range(self.no_of_runs):
            time_taken.append(np.sum(self.results[i][method]["time_per_iter"]) + self.results[i][method]["time_to_cache"])
            train_size = np.array(self.results[i][method]["cost_diff"]).shape[1]*(1-self.results[i][method]["validation_proportion"])
            if i ==0:
                cost_diff_val = np.mean(np.array(self.results[i][method]["cost_diff"])[:,train_size:],axis=1)
                cost_diff_train = np.mean(np.array(self.results[i][method]["cost_diff"])[:,:train_size],axis=1)

            else:
                cost_diff_val = np.vstack([cost_diff_val,np.mean(np.array(self.results[i][method]["cost_diff"])[:,train_size:],axis=1)])
                cost_diff_train = np.vstack([cost_diff_train,np.mean(np.array(self.results[i][method]["cost_diff"])[:,:train_size],axis=1)])
        # return the mean and standard error across runs
        val_mean = np.mean(cost_diff_val,axis=0)
        val_std_err = np.std(cost_diff_val,axis=0)/np.sqrt(self.no_of_runs)
        train_mean = np.mean(cost_diff_train,axis=0)
        train_std_err = np.std(cost_diff_train,axis=0)/np.sqrt(self.no_of_runs)
        time_mean = np.mean(time_taken)
        time_std = np.std(time_taken)
        return train_mean,train_std_err,val_mean,val_std_err,time_mean,time_std

    def plots(self):
        results_for_plots = []
        for r in self.results:
            print r.keys()
        for method in self.results[0].keys():
            results_for_plots.append(self.get_multiple_runs(method))

        f = plt.figure()
        ax = f.add_subplot(111)
        for n,method in enumerate(self.results[0].keys()):
            res = results_for_plots[n]
            ax.errorbar(range(len(res[0])),res[0],label=method,yerr=res[1])
        plt.legend(bbox_to_anchor=(1., 1,0.,-0.06),loc=1)
        ax.set_ylabel("Average Cost difference",fontweight = 'bold',fontsize = 14)
        ax.set_xlabel("Iterations",fontweight='bold',fontsize = 14)
        f.savefig(self.results_dir+"/cost_diff_train.png")

        f = plt.figure()
        ax = f.add_subplot(111)
        for n,method in enumerate(self.results[0].keys()):
            res = results_for_plots[n]
            ax.errorbar(range(len(res[2])),res[2],label=method,yerr=res[3])
        plt.legend(bbox_to_anchor=(1., 1,0.,-0.06),loc=1)
        ax.set_ylabel("Average Cost difference",fontweight = 'bold',fontsize = 14)
        ax.set_xlabel("Iterations",fontweight='bold',fontsize = 14)
        f.savefig(self.results_dir+"/cost_diff_val.png")

        f = plt.figure()
        ax = f.add_subplot(111)
        bar_vals = []
        labl = []
        for n,method in enumerate(self.results[0].keys()):
            labl.append(method)
            res = results_for_plots[n]

            bar_vals.append(np.var(np.concatenate((res[0],res[1]))))
        N = len(self.results[0].keys()) ; ind = np.arange(N)
        width = 0.35
        rects1 = ax.bar(ind, bar_vals, width, color='r')
        ax.set_xticks(ind)
        ax.set_xticklabels(labl)
        plt.legend(bbox_to_anchor=(1., 1,0.,-0.06),loc=1)
        ax.set_ylabel("Variance across iterations",fontweight = 'bold',fontsize = 14)
        f.savefig(self.results_dir+"/var.png")

        



        f = plt.figure()
        ax = f.add_subplot(111)
        for n,method in enumerate(self.results[0].keys()):
            if method[:4] == "RLT_":
                col = "r"
            elif method[:4] == "RLT-":
                col = "b"
            else:
                col = "g"
            if method !="p":
                res = results_for_plots[n]
                print res
                plt.errorbar(res[0][-1],res[-2],label = method,fmt="o",c = col,xerr = res[1][-1])
                plt.annotate(method,xy=(res[0][-1]+0.1,res[-2]+0.1))
        #plt.legend(bbox_to_anchor=(1., 1,0.,-0.06),loc=1)
        ax.set_ylabel("Time Taken (seconds)",fontweight = 'bold',fontsize = 14)
        ax.set_xlabel("Average Cost Difference",fontweight='bold',fontsize = 14)
        f.savefig(self.results_dir+"/pareto_front.png")

        f = plt.figure()
        ax = f.add_subplot(111)
        for n,method in enumerate(self.results[0].keys()):
            if method[:4] == "RLT_":
                col = "r"
            elif method[:4] == "RLT-":
                col = "b"
            else:
                col = "g"
            if method !="p":
                res = results_for_plots[n]
                plt.errorbar(res[2][-1],res[-2],label = method,fmt="o",c = col,xerr = res[3][-1])
                plt.annotate(method,xy=(res[2][-1]+0.1,res[-2]+0.1))
        #plt.legend(bbox_to_anchor=(1., 1,0.,-0.06),loc=1)
        ax.set_ylabel("Time Taken (seconds)",fontweight = 'bold',fontsize = 14)
        ax.set_xlabel("Average Cost Difference",fontweight='bold',fontsize = 14)
        f.savefig(self.results_dir+"/pareto_front_val.png")

        # f = plt.figure()
        # ax = f.add_subplot(111)

        # ax.errorbar(range(len(rrt_res[0])),rrt_res[0],label="RLT*-NC",yerr=rrt_res[1])
        # ax.errorbar(range(len(a08_res[0])),a08_res[0],label="MMP 0.8m",c="g",yerr=a08_res[1])
        # ax.errorbar(range(len(a03_res[0])),a03_res[0],label="MMP 0.3m",c="m",yerr=a03_res[1])
        # #ax.plot(avg_astar02,label="A* 0.2m",c="g")
        # ax.errorbar(range(len(crrt_res[0])),crrt_res[0],label="RLT*",c="r",yerr=crrt_res[1])
        # plt.legend(bbox_to_anchor=(1., 1,0.,-0.06),loc=1)
        # ax.set_ylabel("Average Cost difference",fontweight = 'bold',fontsize = 14)
        # ax.set_xlabel("Iterations",fontweight='bold',fontsize = 14)
        # f.savefig(self.results_dir+"/cost_diff_train.png")

        # f = plt.figure()
        # ax = f.add_subplot(111)
        # ax.errorbar(range(len(rrt_res[2])),rrt_res[2],label="RLT*-NC",yerr=rrt_res[3])
        # ax.errorbar(range(len(a08_res[2])),a08_res[2],label="MMP 0.8m",c="g",yerr=a08_res[3])
        # ax.errorbar(range(len(a03_res[2])),a03_res[2],label="MMP 0.3m",c="m",yerr=a03_res[3])
        # #ax.plot(avg_astar02,label="A* 0.2m",c="g") 
        # ax.errorbar(range(len(crrt_res[2])),crrt_res[2],label="RLT*",c="r",yerr=crrt_res[3])
        # plt.legend(bbox_to_anchor=(1., 1,0.,-0.06),loc=1)
        # ax.set_ylabel("Average Cost difference",fontweight = 'bold',fontsize = 14)
        # ax.set_xlabel("Iterations",fontweight='bold',fontsize = 14)
        # f.savefig(self.results_dir+"/cost_diff_val.png")


    def point_cb(self,msg):
        current_datapoint = self.experiment_data[self.visualization_counter]
        self.ppl_pub.publish(current_datapoint.people)
        self.config_change(current_datapoint.path.poses[0],current_datapoint.people)
        # Publish expert datapoint
        for i in current_datapoint.path.poses:
            i.header.frame_id = "map"
            i.header.stamp = rospy.get_rostime()

        self.costlib.weights = self.results[0]["RLT_10"]["weights_final"]
        #self.costlib.weights = self.gt_weights
        self.expert_path_pub.publish(path_to_pose(current_datapoint.path_array))
        # Plan using initial weights
        self.initial_paths_pub.publish(path_to_pose(self.results[0]["RLT_10"]["initial_paths"][self.visualization_counter]))
        self.crlt_path_pub.publish(path_to_pose(self.results[0]["RLT_10"]["final_paths"][self.visualization_counter]))
        self.astar_08_path_pub.publish(path_to_pose(self.results[0]["MMP_0.8"]["final_paths"][self.visualization_counter]))
        self.astar_03_path_pub.publish(path_to_pose(self.results[0]["MMP_0.3"]["final_paths"][self.visualization_counter]))
        if self.visualization_counter<len(self.experiment_data)-2:
            self.visualization_counter +=1
        else:
            self.visualization_counter=0

    def point_cb_real(self,msg):
        current_datapoint = self.experiment_data[self.visualization_counter]
        self.ppl_pub.publish(current_datapoint.people)
        self.config_change(current_datapoint.path.poses[0],current_datapoint.people)
        # Publish expert datapoint
        for i in current_datapoint.path.poses:
            i.header.frame_id = "map"
            i.header.stamp = rospy.get_rostime()
        self.costlib.weights = self.results[0]["RLT_5"]["weights_final"]
        self.planner._goal  = current_datapoint.goal
        self.planner.update_costmap()
        #self.costlib.weights = self.gt_weights
        self.expert_path_pub.publish(path_to_pose(current_datapoint.path_array))
        # Plan using initial weights
        self.initial_paths_pub.publish(path_to_pose(self.results[0]["RLT_NC_5"]["initial_paths"][self.visualization_counter]))
        self.final_paths_pub.publish(path_to_pose(self.results[0]["RLT_NC_5"]["final_paths"][self.visualization_counter]))
        if self.visualization_counter<len(self.experiment_data)-2:
            self.visualization_counter +=1
        else:
            self.visualization_counter=0

    def config_change(self,robotPose, personPoses):
        rospy.wait_for_service('change_robot_position')
        try:
            robot_pos = rospy.ServiceProxy('change_robot_position', positionChange)
            print "HERE"
            robot_pos(robotPose.pose)
        except rospy.ServiceException, e:
            print "Service call failed: %s"%e

        rospy.wait_for_service('change_people_position')
        try:
            ppl_pos = rospy.ServiceProxy('change_people_position', ppl_positionChange)
            ppl_pos(personPoses)
        except rospy.ServiceException, e:
            print "Service call failed: %s"%e

if __name__=='__main__':
    rospy.init_node('mmp_evaluator')
    m = Evaluator()
    rospy.spin()
