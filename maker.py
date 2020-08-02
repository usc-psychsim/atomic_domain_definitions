#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Jun 20 15:39:15 2020

@author: mostafh
"""
import logging

from psychsim.world import World, WORLD
from psychsim.pwl import makeTree, incrementMatrix, modelKey, rewardKey
from locations_no_pre import Locations
from victims_no_pre import Victims
from ftime import makeExpiryDynamics, incrementTime


def makeWorld(playerName, initLoc, SandRLocs, SandRVics, use_unobserved=True, logger=logging):
    world = World()
    time = world.defineState(WORLD, 'seconds', int)
    world.setFeature(time, 0)
    
    triageAgent = world.addAgent(playerName)
    agent = world.addAgent('ATOMIC')
    
    
    ################# Victims and triage actions
    Victims.world = world
    VICTIMS_LOCS = []
    VICTIM_TYPES = []
    for loc, vics in SandRVics.items():
        for vic in vics:
            if loc.startswith('2'):
                loc = 'R' + loc
            VICTIMS_LOCS.append(loc)
            VICTIM_TYPES.append(vic)
    Victims.world = world
    Victims.COLOR_PRIOR_P = {'Green':0.3, 'Gold':0.4}
    # if the following prob's add up to 1, FOV will never be empty after a search
    Victims.COLOR_FOV_P = {'Green':0.2, 'Gold':0.2, 'Red':0.2, 'White':0.4}
    debug = Victims.setupTriager(VICTIMS_LOCS, VICTIM_TYPES, triageAgent, list(SandRLocs.keys()))
    
    ################# Locations and Move actions
    Locations.EXPLORE_BONUS = 0
    Locations.world = world
    Locations.makeMapDict(SandRLocs)
    Locations.makePlayerLocation(triageAgent,Victims,  initLoc)
    Locations.AllLocations = list(Locations.AllLocations)
    logger.debug('Made move actions')
    
    ################# T I M E
    ## Increment time if none of the durative actions is taken
    incrementTime(world)
    ## Make victim expiration dynamics
    makeExpiryDynamics(Victims.victimsByLocAndColor, Victims.world, Victims.COLOR_EXPIRY)
    ## Reflect victims turning to red on player's FOV  and CH
#    Victims.makeColorChangeDynamics(triageAgent, True, [Victims.STR_CROSSHAIR_VAR, Victims.STR_FOV_VAR], \
#                                    'Red', Locations.AllLocations)
#   
    Victims.makeColorChangeDynamics(triageAgent, True, 'Red', Locations.AllLocations)
   
    ## These must come before setting triager's beliefs
    world.setOrder([{triageAgent.name}])
    
    if not Victims.FULL_OBS:
        if use_unobserved:
            logger.debug('Start to make observable variables and priors')
            Victims.createObsVars4Victims(triageAgent, Locations.AllLocations)
        logger.debug('Made observable variables and priors')
        Victims.makeSearchAction(triageAgent, Locations.AllLocations)
        logger.debug('Made search action')

    triageAgent.resetBelief()
    triageAgent.omega = [key for key in world.state.keys() \
                         if not ((key in {modelKey(agent.name),rewardKey(triageAgent.name)}) or key.startswith('victim')\
                                 or (key.find('unobs')>-1))]
    return world, triageAgent, agent, debug
