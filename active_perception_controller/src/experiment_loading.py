import os
from sklearn.neighbors import NearestNeighbors
from nav_msgs.msg import Path,OccupancyGrid
import rosbag
import rospy
import tf
import numpy as np
from active_perception_controller.msg import Person,PersonArray
from copy import deepcopy
import pdb

class example(object):
    def __init__(self):
        self.path = Path()
        self.people = []
        self.goal =None
        self.path_array = []
        self.goal_xy = None
        self.nbrs = NearestNeighbors(n_neighbors=1,algorithm="kd_tree",leaf_size = 30)

def experiment_load(directory):
    experiment = []
    for subdir,dirs, files in os.walk(directory+'/traj_data/'):
        for file in files:
            print "FILE",file
            bag = rosbag.Bag(directory+'/traj_data/'+file)
            ex = example()
            for topic, msg, t in bag.read_messages():
                if topic == "robot":
                    ex.path.poses.append(msg)
                    ex.path_array.append(np.array([msg.pose.position.x,msg.pose.position.y]))
                elif topic=="people":
                    ex.people.append(msg)
                elif topic == "goal":
                    ex.goal = msg
                    print msg
                    ex.goal_xy = np.array([msg.pose.position.x,msg.pose.position.y])
            bag.close()
            ex.nbrs.fit(ex.path_array)
            experiment.append(deepcopy(ex))
    return experiment

def experiment_load2(directory):
    experiment = []
    for subdir,dirs, files in os.walk(directory+'/traj_data/'):
        for file in files:
            print "FILE",file
            bag = rosbag.Bag(directory+'/traj_data/'+file)
            ex = example()
            for topic, msg, t in bag.read_messages():
                if topic == "path":
                    ex.path = msg
                    for i in msg.poses:
                        ex.path_array.append(np.array([i.pose.position.x,i.pose.position.y]))
                elif topic=="people":
                    ex.people=msg
                elif topic == "goal":
                    ex.goal = msg
                    ex.goal_xy = np.array([msg.pose.position.x,msg.pose.position.y])
            bag.close()
            ex.nbrs.fit(ex.path_array)
            experiment.append(deepcopy(ex))
    return experiment

def euler_from_pose(pose):
    quat = np.zeros(4)
    quat[0] = pose.orientation.x;quat[1] = pose.orientation.y;
    quat[2] = pose.orientation.z;quat[3] = pose.orientation.w
    return tf.transformations.euler_from_quaternion(quat) 
def fill_pose_with_quaternion(pose,quaternion):
    pose.orientation.x = quaternion[0]
    pose.orientation.y = quaternion[1]
    pose.orientation.z = quaternion[2]
    pose.orientation.w = quaternion[3]
    return pose
def zero_orientations_except_z(pose):
    euler = np.zeros(3)
    out = euler_from_pose(pose)
    euler[2]=out[2]
    quat = tf.transformations.quaternion_from_euler(euler[0],euler[1],euler[2])
    pose = fill_pose_with_quaternion(pose,quat)
    return pose
def experiment_load_sevilla(directory,msg_avg = 50):
    experiment = []
    for subdir,dirs, files in os.walk(directory+'/traj_data/'):
        for n,file in enumerate(files):
            print "FILE",file
            bag = rosbag.Bag(directory+'/traj_data/'+file)
            ex = example()
            person1=[];person2=[];goal = []
            for topic, msg, t in bag.read_messages():
                if topic == "/Robot_1/poseStamped":
                    msg.pose = zero_orientations_except_z(msg.pose)
                    ex.path.poses.append(msg)
                    ex.path_array.append(np.array([msg.pose.position.x,msg.pose.position.y]))
                elif topic== "/Person_1/poseStamped":
                    msg.pose = zero_orientations_except_z(msg.pose)
                    person1.append(msg)
                elif topic== "/Person_2/poseStamped":
                    msg.pose = zero_orientations_except_z(msg.pose)
                    person2.append(msg)
                elif topic == "/Person_3/poseStamped":
                    msg.pose = zero_orientations_except_z(msg.pose)
                    goal.append(msg)
            p1 = Person();p1.pose = person1[msg_avg].pose;p1.header.frame_id = "map";p1.id=1
            p2 = Person();p2.pose = person2[msg_avg].pose;p2.header.frame_id = "map";p2.id=2
            p = PersonArray();p.persons = [p1,p2];p.header.frame_id = "map"
            ex.people = p
            ex.goal = ex.path.poses[-1]#;#ex.goal = goal[int(len(goal)/2)]
            ex.goal.header.frame_id = "map"
            ex.goal_xy = np.array([ex.goal.pose.position.x,ex.goal.pose.position.y])
            bag.close()
            ex.nbrs.fit(ex.path_array)
            experiment.append(deepcopy(ex))
    good_traj = [0,1,2,4,6,7,9,10,11,16,17,20,22,23,24,25,26,27,28,30,31,34,36,37,38,39,43]
    e = []
    for i in good_traj:
        e.append(experiment[i])
    e.pop(7)
    return e
