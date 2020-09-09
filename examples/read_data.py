#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr  5 17:00:50 2020

@author: mostafh
"""
import os.path
import sys
from atomic.definitions.map_utils import getSandRMap, getSandRVictims
from atomic.parsing.parser import DataParser
from atomic.scenarios.single_player import make_single_player_world

#	file	player	duration	success	failed	savedGold	savedGreenBe4	savedGreenAft	rooms	moves
# 0	processed_ASIST_data_study_id_000001_condition_id_000003_trial_id_000013_messages.csv	ASU_MC	886.418	22	4	6	0	16	40	173
# 1	processed_ASIST_data_study_id_000001_condition_id_000002_trial_id_000010_messages.csv	ASU_MC	742.332	22	1	5	4	13	41	151
# 2	processed_ASIST_data_study_id_000001_condition_id_000001_trial_id_000008_messages.csv	ASU_MC	739.765	18	0	5	0	13	32	115
# 3	processed_ASIST_data_study_id_000001_condition_id_000002_trial_id_000002_messages.csv	K_Fuse	603.21	22	0	6	3	13	39	133
# 4	processed_ASIST_data_study_id_000001_condition_id_000003_trial_id_000006_messages.csv	K_Fuse	1215.312	19	2	6	0	13	41	159
# 5	processed_ASIST_data_study_id_000001_condition_id_000002_trial_id_000003_messages.csv	K_Fuse	648.278	19	0	6	7	6	41	148
# 6	processed_ASIST_data_study_id_000001_condition_id_000001_trial_id_000005_messages.csv	K_Fuse	607.1	4	3	2	1	1	17	37
# 7	processed_ASIST_data_study_id_000001_condition_id_000001_trial_id_000001_messages.csv	K_Fuse	394.472	3	1	2	1	0	11	23


#### Parse the data file into a sequence of actions and events
try:
    parser = DataParser(os.path.join(os.path.dirname(__file__), 'data', sys.argv[1]))
except IndexError:
    parser = DataParser(os.path.join(os.path.dirname(__file__), 'data',
                                     'processed_ASIST_data_study_id_000001_condition_id_000003_trial_id_000013_messages.csv'))
name = parser.player_name()

#
####### Get Map Data
small = False
SandRLocs = getSandRMap(small)
SandRVics = getSandRVictims(small)

world, triageAgent, agent, victimsObj, world_map = make_single_player_world(name, 'BH2', SandRLocs, SandRVics)

### Replay sequence of actions and events
aes, data = parser.getActionsAndEvents(triageAgent.name, victimsObj, world_map, True, 50)
# DataParser.runTimeless(world, triageAgent.name, aes,  0, 148, 0)
