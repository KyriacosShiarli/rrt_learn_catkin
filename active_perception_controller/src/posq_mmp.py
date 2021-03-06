#!/usr/bin/env python
import tf
import pdb
import rospy
import roslib
import time
import threading
import numpy as np
import scipy as sp
import os
import itertools
import cProfile, pstats, StringIO
import rosbag
import helper_functions as fn
from geometry_msgs.msg import Pose
from geometry_msgs.msg import PoseStamped
from math import *
from nav_msgs.srv import GetMap
from nav_msgs.msg import Path,OccupancyGrid
from sklearn.neighbors import NearestNeighbors
from StringIO import StringIO
from geometry_msgs.msg._PoseStamped import PoseStamped
from visualization_msgs.msg import Marker,MarkerArray
from helper_functions import pixel_to_point
from active_perception_controller.srv import positionChange,ppl_positionChange
from motion_planner_posq import MotionPlanner
from active_perception_controller.msg import Person,PersonArray
from random import shuffle
from experiment_loading import example,experiment_load2,experiment_load_sevilla

CURRENT = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.split(CURRENT)[0]


class Learner(object):
    def __init__(self):
        self.iterations = rospy.get_param("~iterations", 10)
        self.learning_rate = rospy.get_param("~learning_rate", 0.5)
        self.time_margin_factor = rospy.get_param("~time_margin_factor", 1.0)
        self.cache_size = rospy.get_param("~point_cache_size", 2500)
        self.momentum = 0.2
        self.exp_name = rospy.get_param("~experiment_name", "posq_test_exp3")
        self.session_name = rospy.get_param("~session_name", "posq_learn_test_fast")
        self.baseline_eval = rospy.get_param("~baseline", True)
        self.path = PARENT
        self.directory = self.path+"/data/"+self.exp_name
        self.results_dir = self.path+"/results/"+self.session_name+"/"
        fn.make_dir(self.results_dir)
        self.experiment_data = experiment_load2(self.directory)
        self.planner = MotionPlanner()
        self.validation_proportion = rospy.get_param("~validation_proportion", 0.5)
        self.costlib = self.planner.cost_manager
        self.ppl_pub =  rospy.Publisher("person_poses",PersonArray,queue_size = 10)
        if self.baseline_eval==True:
            try:
                loaded = fn.pickle_loader(self.directory+"/weights.pkl")
                self.gt_weights = loaded["weights"]
                self.gt_featureset = loaded["feature_set"]
            except:
                self.gt_weights=None
                self.baseline_eval=False

        self.write_learning_params(self.results_dir)
        #self.sevilla_test_run("1")
        self.single_run("2")
    def write_learning_params(self,directory):
        f = open(directory+"readme","w")
        f.write("Learning parameters used: \n------ \n \n")
        f.write("Experiment name:  "+ self.exp_name +"\n")
        f.write("Iteration:  "+ str(self.iterations) +"\n")
        f.write("learning_rate:  "+ str(self.learning_rate) +"\n")
        f.write("validation_proportion:  "+ str(self.validation_proportion) +"\n")
        f.close()        

    def sevilla_test_run(self,name):
        results = {}
        self.planner.planning_time = 100;self.planner.max_planning_time = 120
        self.cache_size = 1200
        results["RLT_NC_5"]= self.learning_loop(self.planner,planner_type="rrtstar")
        results["RLT_5"]=  self.learning_loop(self.planner,planner_type="cached_rrt")
        fn.pickle_saver(results,self.results_dir+"results_"+name+".pkl")

    def single_run(self,name):
        self.planner.planning_time = 140;self.planner.max_planning_time = 160
        self.cache_size = 2500
        results_rrtstar = self.learning_loop(self.planner,planner_type="rrtstar")
        #results_cached_rrt = self.learning_loop(self.planner,planner_type="cached_rrt")
        results = {"rlt-nc":results_rrtstar}
        fn.pickle_saver(results,self.results_dir+"results_"+name+".pkl")
    def variance_run(self,name):
        self.planner.planning_time = 10;self.planner.max_planning_time = 15
        nc_300 = self.learning_loop(self.planner,planner_type="rrtstar")

        #self.planner.planning_time = 300;self.planner.max_planning_time = 320
        #nc_300 = self.learning_loop(self.planner,planner_type="rrtstar")
        #self.planner.planning_time = 50;self.planner.max_planning_time = 60
        #nc_50 = self.learning_loop(self.planner,planner_type="rrtstar")
        #self.planner.planning_time = 100;self.planner.max_planning_time = 120
        #nc_100 = self.learning_loop(self.planner,planner_type="rrtstar")
        #self.planner.planning_time = 200;self.planner.max_planning_time = 220
        #nc_200 = self.learning_loop(self.planner,planner_type="rrtstar")

        #results_rrtstar = self.learning_loop(self.planner,planner_type="rrtstar")
        results_cached_rrt = self.learning_loop(self.planner,planner_type="cached_rrt")
        results = {"rlt-nc_300":nc_300}
        fn.pickle_saver(results,self.results_dir+"results_"+name+".pkl")

    def learning_loop(self,motion_planner,planner_type = "rrtstar"):

        # some time bookkeeping
        if planner_type == "rrtstar":
            motion_planner.planner = planner_type
            time_to_cache=0
        elif planner_type =="cached_rrt":
            motion_planner.planner = "rrtstar"
            cached_trees = []
            time_to_cache = []

        # Initialise weights.
        self.learner_weights = np.zeros(self.costlib.weights.shape[0])
        self.learner_weights[1] = 4
        self.learner_weights[0] = 1# some cost for distance
        validating = False
        similarity = []
        cost_diff = []
        time_taken = []
        initial_paths = []
        final_paths = []
        all_feature_sums = []
        gradient_store = []
        for n,i in enumerate(self.experiment_data):
            self.ppl_pub.publish(i.people)
            rospy.sleep(1.)
            i.feature_sum = self.feature_sums(i.path_array,i.goal_xy)

            print "FEATURE SUM", i.feature_sum
            all_feature_sums.append(i.feature_sum/len(i.path_array))
            if self.baseline_eval == True:
                self.costlib.set_featureset(self.gt_featureset)
                i.gt_feature_sum =self.feature_sums(i.path_array,i.goal_xy)
                i.path_cost = np.dot(self.gt_weights,i.gt_feature_sum)
                self.costlib.set_featureset(self.planner.planning_featureset)
        feature_sum_variance = np.var(np.array(all_feature_sums),axis = 0)


        for iteration in range(self.iterations):
            prev_grad = 0
            print "####################ITERATION",iteration
            iter_similarity = []
            iter_cost_diff = []
            iter_time = []

            iter_grad = np.zeros(self.learner_weights.shape[0])
            self.costlib.weights = self.learner_weights
            self.initial_weights = np.copy(self.learner_weights)
            print "DATA LENGTH",len(self.experiment_data)
            for n,i in enumerate(self.experiment_data):
                print "DATA POINT",n
                print "ITERATION",iteration
                if n>=len(self.experiment_data)*(1-self.validation_proportion):
                    validating = True
                else:
                    validating = False
                print "CHANGING POSITION"
                self.planner.publish_empty_path()
                
                config_change(i.path.poses[0],i.people)
                rospy.sleep(1.)
                self.planner._goal = i.goal

                if validating==False and planner_type=="cached_rrt" and iteration==0:
                    tic = time.time()
                    cached_trees.append(motion_planner.make_cached_rrt(motion_planner.sample_goal_bias,points_to_cache=self.cache_size))
                    toc = time.time()
                    time_to_cache.append(toc-tic) 

                if validating==False:
                    self.costlib.ref_path_nn = i.nbrs
                    tic = time.time()
                    if planner_type!="cached_rrt":
                        # if there is a time margin factor it will be used during the learning planning step
                        motion_planner.planning_time*=self.time_margin_factor
                        pose_path_la,array_path_la = motion_planner.plan()
                    else:
                        pose_path_la,array_path_la = motion_planner.plan_cached_rrt(cached_trees[n])
                    array_path_la = array_path_la[:,:2]
                    toc = time.time()
                    iter_time.append(toc-tic)

                self.costlib.ref_path_nn = None
                # recover time margin factor to normal planning time.
                motion_planner.planning_time*=1/self.time_margin_factor
                pose_path,array_path = motion_planner.plan()
                array_path = array_path[:,:2]

                if iteration ==0:
                    initial_paths.append(array_path)
                elif iteration == self.iterations-1:
                    final_paths.append(array_path)

                rospy.sleep(0.5)

                if validating == False:
                    path_feature_sum_la = self.feature_sums(array_path_la,i.goal_xy)
                    iter_grad+= self.learner_weights*0.00 + (i.feature_sum - path_feature_sum_la)#/feature_sum_variance
                    print "GRADIENT", (i.feature_sum - path_feature_sum_la)#/feature_sum_variance#

                path_feature_sum = self.feature_sums(array_path,i.goal_xy)
                # Baseline evaluation if possible.
                if self.baseline_eval == True:
                    #calculate featuresums based on the ground truth featureset whatever that is
                    self.costlib.set_featureset(self.gt_featureset)
                    gt_feature_sum = self.feature_sums(array_path,i.goal_xy)
                    path_base_cost = np.dot(self.gt_weights,gt_feature_sum)
                    iter_cost_diff.append(path_base_cost - i.path_cost)
                    self.costlib.set_featureset(self.planner.planning_featureset)
                print "COST DIFFERENCE", iter_cost_diff
                          
                print "PATH FEATURE SUM",path_feature_sum
                print "PAth Feature SUM LA",path_feature_sum_la
                iter_similarity.append(self.get_similarity(i.path_array,array_path))
            gradient_store.append(iter_grad/(len(self.experiment_data)*(1-self.validation_proportion)))
            grad = (1-self.momentum)*iter_grad/(len(self.experiment_data)*(1-self.validation_proportion)) + self.momentum*prev_grad
            self.learner_weights = self.learner_weights - self.learning_rate*grad
            prev_grad = grad
            idx = np.where(self.learner_weights<0)
            self.learner_weights[idx]=0
            print "WEIGHTS",self.learner_weights
            print "GRADIENT ", grad
            similarity.append(np.array(iter_similarity))
            cost_diff.append(np.array(iter_cost_diff))
            time_taken.append(np.array(iter_time))

        print cost_diff
        results = {"similarity":similarity,"cost_diff":cost_diff,
                "weights_final":self.learner_weights,"weights_initial":self.initial_weights,
                 "initial_paths":initial_paths,"final_paths":final_paths,"validation_proportion":self.validation_proportion,"gradients":gradient_store,"time_to_cache":time_to_cache,"time_per_iter":time_taken}

        return results

    def feature_sums(self,xy_path,goal_xy,interpolation=True):
        # calculates path feature sums.
        if interpolation==True:
            xy_path = interpolate_path(xy_path,resolution=0.005)
        feature_sum = 0
        for i in range(len(xy_path)-1):
            if i ==0:
                f1 = self.costlib.featureset(xy_path[i],goal_xy)
                f2 = self.costlib.featureset(xy_path[i+1],goal_xy)
                feature_sum= self.costlib.edge_feature(f1,f2,xy_path[i],xy_path[i+1])
            else:
                f1 = self.costlib.featureset(xy_path[i],goal_xy)
                f2 = self.costlib.featureset(xy_path[i+1],goal_xy)
                feature_sum+= self.costlib.edge_feature(f1,f2,xy_path[i],xy_path[i+1])
        return feature_sum
   

    def get_similarity(self,example_path,learner_path):
        # inputs are the example and learner path in xy.
        nbrs = NearestNeighbors(n_neighbors=1,algorithm="kd_tree",leaf_size = 30)
        nbrs.fit(np.array(learner_path))
        (dist, idx) = nbrs.kneighbors(example_path)
        return np.sum(dist)

    def test_similarity(self):
        ex1 = self.experiment_data[0].path_array
        ex2 = self.experiment_data[1].path_array
        sim = self.get_similarity(ex1,ex2)
        return sim
    def test_feature_sum(self):
        self.ppl_pub.publish(self.experiment_data[0].people[0])
        rospy.sleep(0.1)
        fs = self.feature_sums(self.experiment_data[0].path_array,self.experiment_data[0].goal_xy)
        return fs

def interpolate_path(path,resolution=0.2):
    new_path = None
    for n in range(len(path)-1):
        diff = path[n+1] - path[n]
        segments = np.floor(np.linalg.norm(diff)/resolution)

        x_arr = np.linspace(0,diff[0],segments)
        y_arr = np.linspace(0,diff[1],segments)
        inter = path[n] + np.append([x_arr],[y_arr],axis=0).T

        if n==0:
            new_path = inter
        else:
            new_path = np.append(new_path,inter,axis=0)
    return new_path

def config_change(robotPose, personPoses):
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
    rospy.init_node('mmp_learner')
    m = Learner()
    rospy.spin()
