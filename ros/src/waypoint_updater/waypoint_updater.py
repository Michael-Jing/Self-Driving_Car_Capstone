#!/usr/bin/env python

import rospy
import math
import tf
from   geometry_msgs.msg import PoseStamped, TwistStamped
from   styx_msgs.msg     import Lane, Waypoint
from   std_msgs.msg      import Int32


LOOKAHEAD_WPS = 200
MAX_DECEL     = 4.0
STOP_BUFFER   = 5.0


class WaypointUpdater(object):

    def __init__(self):
        rospy.init_node('waypoint_updater')

        rospy.Subscriber('/current_pose',      PoseStamped, self.current_pose_cb)
        rospy.Subscriber('/base_waypoints',    Lane,        self.base_waypoints_cb)
        rospy.Subscriber('/traffic_waypoint',  Int32,       self.traffic_waypoint_cb)
        rospy.Subscriber('/obstacle_waypoint', Int32,       self.obstacle_waypoint_cb)
        rospy.Subscriber('/current_velocity',  TwistStamped,self.current_velocity_cb)

        self.current_velocity = 0.0
        self.decel = 1.0
        self.traffic_waypoint = -1
        self.braking = False

        self.final_waypoints_pub = rospy.Publisher('final_waypoints', Lane, queue_size=1)

        rate = rospy.Rate(10)
        while not rospy.is_shutdown():
            self.loop()
            rate.sleep()


    def loop(self):
        if hasattr(self, 'base_waypoints') and hasattr(self, 'current_pose'):
            lane                 = Lane()
            lane.header.stamp    = rospy.Time().now()
            lane.header.frame_id = '/world'

            pose = self.current_pose
            wpts = self.base_waypoints.waypoints

            next_wp    = self.get_next_waypoint(pose, wpts)
            traffic_wp = self.traffic_waypoint

            # Get current distance from traffic light and minimum distance need to stop
            tl_dist = self.distance(pose.pose.position, wpts[traffic_wp].pose.pose.position)

            # The distance of speed lower down to zero, plus the distance of the road cross
            min_stopping_dist = self.current_velocity**2 / (2.0 * MAX_DECEL) + STOP_BUFFER

            # 1 If at any time, the red light disappeared, run the car normally
            if traffic_wp == -1:
                self.braking = False
                lane.waypoints = self.get_final_waypoints(wpts, next_wp, next_wp+LOOKAHEAD_WPS)

            # Froce stop attempt
            # elif tl_dist > STOP_BUFFER and self.current_velocity < 5:
            #     self.braking = True
            #     lane.waypoints = self.force_brake(wpts, next_wp, traffic_wp)

            #2 If red light is detected,the car is still in running mode and the distance is too short, dont stop
            #  To make it fancier and more related to the real, it should be accelerate
            elif not self.braking and tl_dist < min_stopping_dist:
                lane.waypoints = self.get_final_waypoints(wpts, next_wp, next_wp+LOOKAHEAD_WPS)

            #3 Make a stop process
            else:
                self.braking = True
                lane.waypoints = self.get_final_waypoints(wpts, next_wp, traffic_wp)

            self.final_waypoints_pub.publish(lane)


    def get_final_waypoints(self, waypoints, start_wp, end_wp):
        final_waypoints = []
        for i in range(start_wp, end_wp):
            index = i % len(waypoints)
            wp = Waypoint()
            wp.pose.pose.position.x  = waypoints[index].pose.pose.position.x
            wp.pose.pose.position.y  = waypoints[index].pose.pose.position.y
            wp.pose.pose.position.z  = waypoints[index].pose.pose.position.z
            wp.pose.pose.orientation = waypoints[index].pose.pose.orientation

            if not self.braking:
                #waypoints is the base_waypoints
                # wp.twist.twist.linear.x = waypoints[index].twist.twist.linear.x
                wp.twist.twist.linear.x = 15.0
            else:
                # Slowly creep up to light if we have stopped short
                dist = self.distance(wp.pose.pose.position, waypoints[end_wp].pose.pose.position)
                if dist > STOP_BUFFER and self.current_velocity < 3.0:
                    wp.twist.twist.linear.x = 3.0
                # Force stop
                elif dist <= STOP_BUFFER:
                    wp.twist.twist.linear.x = 0.0
                else:
                    #wp.twist.twist.linear.x = min(2.0, waypoints[index].twist.twist.linear.x)
                    if(self.current_velocity - i >3.0):
                        wp.twist.twist.linear.x = self.current_velocity - i * 0.5
                    else:
                        wp.twist.twist.linear.x = 3.0

            final_waypoints.append(wp)

        return final_waypoints

    def distance(self, p1, p2):
        x = p1.x - p2.x
        y = p1.y - p2.y
        z = p1.z - p2.z
        return math.sqrt(x*x + y*y + z*z)


    def current_pose_cb(self, msg):
        self.current_pose = msg


    def base_waypoints_cb(self, msg):
        self.base_waypoints = msg


    def traffic_waypoint_cb(self, msg):
        self.traffic_waypoint = msg.data


    def current_velocity_cb(self, msg):
        self.current_velocity = msg.twist.linear.x


    def obstacle_waypoint_cb(self, msg):
        self.obstacle_waypoint = msg.data


    def get_closest_waypoint(self, pose, waypoints):
        closest_dist = float('inf')
        closest_wp = 0
        for i in range(len(waypoints)):
            dist = self.distance(pose.pose.position, waypoints[i].pose.pose.position)
            if dist < closest_dist:
                closest_dist = dist
                closest_wp = i

        return closest_wp


    def get_next_waypoint(self, pose, waypoints):
        closest_wp = self.get_closest_waypoint(pose, waypoints)
        wp_x = waypoints[closest_wp].pose.pose.position.x
        wp_y = waypoints[closest_wp].pose.pose.position.y
        heading = math.atan2( (wp_y-pose.pose.position.y), (wp_x-pose.pose.position.x) )
        x = pose.pose.orientation.x
        y = pose.pose.orientation.y
        z = pose.pose.orientation.z
        w = pose.pose.orientation.w
        euler_angles_xyz = tf.transformations.euler_from_quaternion([x,y,z,w])
        theta = euler_angles_xyz[-1]
        angle = math.fabs(theta-heading)
        if angle > math.pi / 4.0:
            closest_wp += 1

        return closest_wp


if __name__ == '__main__':
    try:
        WaypointUpdater()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start waypoint updater node.')