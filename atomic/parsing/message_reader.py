#!/usr/bin/env python3

# read necessary portions of message buffer for psychsim
# can call on entire file or request latest event

from builtins import range
import os
import sys
import time
import functools
import json
import math
import csv
print = functools.partial(print, flush=True)

class room(object):
    def __init__(self, name, x0, z0, x1, z1):
        self.name = name

        self.xrange = range(x0,x1) 
        self.zrange = range(z0,z1)

    def in_room(self, _x, _z):
        if _x in self.xrange and _z in self.zrange:
            return True   
        else:
            return False

class door(object):
    def __init__(self, x0, z0, x1, z1, room1, room2):
        self.room1 = room1
        self.room2 = room2
        self.x0 = x0
        self.x1 = x1
        self.z0 = z0
        self.z1 = z1
        self.center = [x0,z0] # default to corner
        self.xrange = range(x0,x1+1)
        self.zrange = range(z0,z1+1)
        # calc center half the span of x & z 
        xlen = math.floor(abs(x0 - x1)/2)
        zlen = math.floor(abs(z0 - z1)/2)
        self.center = [x0+xlen,z0+zlen]

    def at_this_door(self, _x, _z):
        if _x in self.xrange and _z in self.zrange:
            return True
        else:
            return False

class msg(object):
    def __init__(self, msg_type):
        self.mtype = msg_type
        self.mdict = {}

class msgreader(object):
    def __init__(self, fname, latest=False):
        self.psychsim_tags = ['mission_timer', 'sub_type'] # maybe don't need here
        self.nmessages = 0
        self.rooms = []
        self.doors = [] # actually portals
        self.msg_types = ['Event:Triage', 'Event:Door', 'Event:Lever', 'Event:VictimsExpired', 'Mission:VictimList', 'Event:Beep', 'FoV']
        self.messages = []
        self.mission_running = False
        self.locations = []
        self.observations = []

    def get_all_messages(self,fname):
        message_arr = []
        jsonfile = open(fname, 'rt')
        for line in jsonfile.readlines():
            if line.find('data') > -1:
                m = self.parse_message(line)
                if (len(m.items()) > 0):
                    message_arr.append(m)
            jsonfile.close()
        return message_arr

    # find closest portal (closest room may not be accessible)
    # then find the rooms that portal adjoins & select the one we're not already in
    def find_beep_room(self,x,z):
        best_dist = 99999
        agent_room = ''
        beep_room = 'null'
        didx = 0
        bestd = 0
        for r in self.rooms:
            if r.in_room(x,z):
                agent_room = r.name
        for d in self.doors:
            dx = d.center[0]
            dz = d.center[1]
            distance = math.sqrt(pow((dx-x),2) + pow((dz-z),2))
            if distance < best_dist:
                best_dist = distance
                bestd = didx
                # now choose whichever room not already in
                if agent_room == d.room1:
                    beep_room = d.room2
                else:
                    beep_room = d.room1
            didx += 1
        return beep_room

    def get_obs_timer(self,fmessage):
        obsnum = fmessage.mdict['observation']
        nobs = len(self.observations)
        oidx = nobs-1
        timer = ''
        while oidx >= 0:
            if obsnum == self.observations[oidx][0]: # we have a match
                timer = self.observations[oidx][1]
            oidx -= 1
        #return timer
        fmessage.mdict.update({'mission_timer':timer})

    # add to msgreader obj
    # TODO: add counter to know nlines btwn start/stop
    def add_all_messages(self,fname):
        message_arr = []
        jsonfile = open(fname, 'rt')
        nlines = 0
        for line in jsonfile.readlines():
            # first filter messages before mission start & record observations
            if line.find("mission_victim_list") > -1:
                self.mission_running = True # count this as mission start, start will occur just after list
                self.add_message(line)
            elif line.find("mission_state\":\"Stop") > -1:
                self.mission_running = False
            elif line.find("paused\":true") > -1:
                self.mission_running = False
            elif line.find("paused\":false") > -1:
                self.mission_running = True
            elif line.find('observation_number') > -1 and self.mission_running:
                self.add_observation(line)
            # now get actual messages
            elif line.find('data') > -1: 
                self.add_message(line)
            # if line.find('Event:Location'):
            #    self.add_location(line)
            nlines += 1
        jsonfile.close()

    # adds single message to msgreader.messages list
    def add_message(self,jtxt): 
        add_msg = True
        m = self.make_message(jtxt) # generates message, sets psychsim_tags
        if m.mtype in self.msg_types and self.mission_running:
            obs = json.loads(jtxt)
            message = obs[u'msg']
            data = obs[u'data']
            m.mdict = {}
            for (k,v) in data.items():
                if k in self.psychsim_tags:
                    m.mdict[k] = v
            for (k,v) in message.items():
                if k in self.psychsim_tags:
                    m.mdict[k] = v
            if m.mtype in ['Event:Triage', 'Event:Lever']:
                self.add_room(m.mdict,m.mtype)            
            elif m.mtype == 'Event:Door':
                self.add_door_rooms(m.mdict,m.mtype)
            elif m.mtype == 'Mission:VictimList':
                self.make_victims_msg(jtxt,m)
            elif m.mtype == 'Event:Beep':
                room_name = self.find_beep_room(int(m.mdict['beep_x']), int(m.mdict['beep_z']))
                del m.mdict['beep_x']
                del m.mdict['beep_z']
                m.mdict.update({'room_name':room_name})
            elif m.mtype == 'FoV':
                self.get_obs_timer(m)
                if jtxt.find('victim') == -1 or m.mdict['mission_timer'] == '': # no victims skip msg
                    add_msg = False
                else:
                    del m.mdict['observation']
                    self.get_fov_blocks(m,jtxt)
            if add_msg:
                self.messages.append(m)

    # *might* have to filer out uninitialized timer
    def add_observation(self,jtxt):
        obs = json.loads(jtxt)
        # message = obs[u'msg']
        data = obs[u'data']
        obsnum = int(data['observation_number'])
        mtimer = data['mission_timer']
        self.observations.append([obsnum,mtimer])

    def get_fov_blocks(self,m,jtxt):
        victim_arr = []
        obs = json.loads(jtxt)
        data = obs[u'data']
        blocks = data['blocks']
        for b in blocks:
            if b['type'].find('victim') > -1:
                victim_arr.append(b['type'])
        m.mdict.update({'victim_list':victim_arr})
      
    def make_victims_msg(self,line,vmsg):
        psychsim_tags = ['sub_type','message_type', 'mission_victim_list']
        victim_list_dicts = []
        obs = json.loads(line)
        header = obs[u'header']
        msg = obs[u'msg']
        victims = obs[u'data']
        for (k,v) in msg.items():
            if k in psychsim_tags:
                vmsg.mdict.update({k:v})
        for (k,v) in header.items():
            if k in psychsim_tags:
                vmsg.mdict.update({k:v})
        for (k,v) in victims.items():
            if k == 'mission_victim_list':
                victim_list_dicts = v
        for victim in victim_list_dicts:
            room_name = 'null'
            for (k,v) in victim.items():
                if k == 'x':
                    vx = v
                elif k == 'z':
                    vz = v
            for r in self.rooms:
                if r.in_room(vx,vz):
                    room_name = r.name
            del victim['x']
            del victim['y']
            del victim['z']
            victim.update({'room_name':room_name})
        vmsg.mdict.update({'mission_victim_list':victim_list_dicts})
        del vmsg.mdict['mission_timer']

    # adds which room event is occurring in 
    def add_room(self, msgdict, msg_type):
        x = 0
        z = 0
        xkey = ''
        zkey = ''
        room_name = ''
        for (k,v) in msgdict.items():
            if k.find('_x') > -1:
                x = float(v)
                xkey = k
            elif k.find('_z') > -1:
                z = int(v)
                zkey = k
        for r in self.rooms:
            if r.in_room(x,z):
                room_name = r.name
        del msgdict[xkey]
        del msgdict[zkey]

        msgdict.update({'room':room_name})

    def add_door_rooms(self, msgdict, msg_type):
        doors_found = 0
        x = 0
        z = 0
        for (k,v) in msgdict.items():
            if k.find('_x') > -1:
                x = float(v)
            elif k.find('_z') > -1:
                z = int(v)
        for d in self.doors:
            if d.at_this_door(x,z):
                msgdict.update({'room1':d.room1})
                msgdict.update({'room2':d.room2})
                del msgdict['door_x'] # no longer needed once have ajoining rooms
                del msgdict['door_z']
                doors_found += 1
        # if we did not find this door's adjoining rooms, it's not a portal, still need to update its fields
        if doors_found == 0:
            msgdict.update({'room1':'null'})
            msgdict.update({'room2':'null'})
            del msgdict['door_x'] # no longer needed once have ajoining rooms
            del msgdict['door_z']
        
    # check what kind of event to determine tags to look for
    # if doesn't match any, we don't care about it so
    # message won't be processed
    def make_message(self,jtxt):
        m = msg('NONE')
        self.psychsim_tags = ['sub_type', 'mission_timer', 'playername']
        if jtxt.find('Event:Triage') > -1:
            self.psychsim_tags += ['triage_state', 'color', 'victim_x', 'victim_z']
            m.mtype = 'Event:Triage'
        elif jtxt.find('Event:Door') > -1:
            self.psychsim_tags += ['open', 'door_x', 'door_z', 'room1', 'room2']
            m.mtype = 'Event:Door'
        elif jtxt.find('Event:Lever') > -1:
            self.psychsim_tags += ['powered', 'lever_x', 'lever_z']
            m.mtype = 'Event:Lever'
        elif jtxt.find('Event:VictimsExpired') > -1:
            self.psychsim_tags += ['mission_timer']
            m.mtype = 'Event:VictimsExpired'
        elif jtxt.find('Mission:VictimList') > -1:
            self.psychsim_tags += ['mission_victim_list', 'room_name', 'message_type']
            m.mtype = 'Mission:VictimList'
        elif jtxt.find('Event:Beep') > -1:
            self.psychsim_tags += ['message', 'room_name', 'beep_x', 'beep_z']
        elif jtxt.find('FoV') > -1:
            self.psychsim_tags += ['observation']
            m.mtype = 'FoV'
        return m

    # this will be updated to use mmap, for now reads all lines
    # returns empty dict if no new messages
    def get_latest_message(self, fname):
        jsonfile = open(fname, 'rt')
        laststr = ''
        msgcnt = 0
        lastmsg = {}
        for line in jsonfile.readlines():
            laststr = line
            msgcnt += 1
        jsonfile.close()
        if msgcnt > self.nmessages and laststr.find('data') > -1:
            lastmsg = self.parse_message(laststr)
        return lastmsg

    def load_rooms(self, fname):
        with open(fname) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            line_count = 0
            for row in csv_reader:
                if line_count == 0:
                    line_count += 1
                else:
                    r = room(str(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4]))
                    self.rooms.append(r)
                    line_count += 1

    def load_doors(self, fname):
        with open(fname) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            line_count = 0
            for row in csv_reader:
                if line_count == 0:
                    line_count += 1
                else:
                    d = door(int(row[1]), int(row[2]), int(row[3]), int(row[4]), str(row[5]), str(row[6]))
                    self.doors.append(d)
                    line_count += 1

# USE: create reader object then use to read either last message in file -- returns single dict
# or all messages in file -- returns array of dictionaries
jsonfile = '/home/skenny/usc/asist/data/study-1_2020.08_TrialMessages_CondBtwn-NoTriageNoSignal_CondWin-FalconEasy-StaticMap_Trial-120_Team-na_Member-51_Vers-1.metadata'
reader = msgreader(jsonfile, True)
reader.load_rooms('/home/skenny/usc/asist/data/ASIST_FalconMap_Rooms_v1.1_OCN.csv')
reader.load_doors('/home/skenny/usc/asist/data/ASIST_FalconMap_Portals_v1.1_OCN.csv')
# singlemsg = reader.get_latest_message(jsonfile)
reader.add_all_messages(jsonfile)
# print all the messages
for m in reader.messages:
    print(str(m.mdict))