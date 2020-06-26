import logging
import os
from psychsim.helper_functions import get_true_model_name
from psychsim.probability import Distribution
from psychsim.pwl import modelKey, rewardKey, stateKey, makeTree, setToConstantMatrix
from model_learning.inference import track_reward_model_inference
from model_learning.trajectory import generate_trajectory
from model_learning.util.io import create_clear_dir
from model_learning.util.plot import plot_evolution
from SandRMap import getSandRMap, getSandRVictims
from maker import makeWorld
from victims_clr import Victims

__author__ = 'Pedro Sequeira'
__email__ = 'pedrodbs@gmail.com'
__description__ = 'Perform reward model inference in the ASIST world based on human player data.' \
                  'There is an observer agent that has 4 models of the moving agent (uniform prior):' \
                  '  - a model with the true reward function;' \
                  '  - a model with a zero reward function, resulting in a random behavior;' \
                  '  - other models with different weights for each victim type.' \
                  'We collect a trajectory where the world is updated for some steps and the observer updates its ' \
                  'belief over the models of the triaging agent via PsychSim inference. ' \
                  'A plot is show with the inference evolution.'

NUM_STEPS = 100

OBSERVER_NAME = 'ATOMIC'
AGENT_NAME = 'Player173'
YELLOW_VICTIM = 'Gold'
GREEN_VICTIM = 'Green'

# models
PREFER_NONE_MODEL = 'prefer_none'
PREFER_YELLOW_MODEL = 'prefer_yellow'
PREFER_GREEN_MODEL = 'prefer_green'
RANDOM_MODEL = 'zero_rwd'

# agents properties
HORIZON = 1
MODEL_SELECTION = 'distribution'  # TODO 'consistent' or 'random' gives an error
MODEL_RATIONALITY = .5
AGENT_SELECTION = 'random'

# victim reward values
HIGH_VAL = 200
LOW_VAL = 10
MEAN_VAL = (HIGH_VAL + LOW_VAL) / 2

OUTPUT_DIR = 'output/reward-model-inference'
DEBUG = False
SHOW = True
INCLUDE_RANDOM_MODEL = False
FULL_OBS = False


def _get_fancy_name(name):
    return name.title().replace('_', ' ')


if __name__ == '__main__':
    # sets up log to screen
    logging.basicConfig(format='%(message)s', level=logging.DEBUG if DEBUG else logging.INFO)

    # create output
    create_clear_dir(OUTPUT_DIR)

    # MDP or POMDP
    Victims.FULL_OBS = FULL_OBS

    # create world, agent and observer
    world, agent, _ = makeWorld(AGENT_NAME, 'BH2', getSandRMap(), getSandRVictims())
    agent.setAttribute('horizon', HORIZON)
    agent.setAttribute('selection', AGENT_SELECTION)
    observer = world.agents[OBSERVER_NAME]

    # observer does not model itself
    observer.resetBelief(ignore={modelKey(observer.name)})

    # agent does not model itself and sees everything except true models and its reward
    agent.resetBelief(ignore={modelKey(observer.name)})
    agent.omega.extend([key for key in world.state.keys()
                        if key not in {rewardKey(agent.name), modelKey(observer.name)}])

    # get the canonical name of the "true" agent model
    true_model = get_true_model_name(agent)

    # reward models (as linear combinations of victim color)
    mm_list = {
        PREFER_NONE_MODEL: {GREEN_VICTIM: MEAN_VAL, YELLOW_VICTIM: MEAN_VAL},
        PREFER_GREEN_MODEL: {GREEN_VICTIM: HIGH_VAL, YELLOW_VICTIM: LOW_VAL},
        PREFER_YELLOW_MODEL: {GREEN_VICTIM: LOW_VAL, YELLOW_VICTIM: HIGH_VAL}  # should be the most likely at the end
    }
    for name, rwd_dict in mm_list.items():
        if name != true_model:
            agent.addModel(name, parent=true_model, rationality=MODEL_RATIONALITY, selection=MODEL_SELECTION)
        Victims.makeVictimReward(agent, name, rwd_dict)

    if INCLUDE_RANDOM_MODEL:
        agent.addModel(RANDOM_MODEL, parent=true_model, rationality=.5, selection=MODEL_SELECTION)
        agent.setReward(makeTree(setToConstantMatrix(rewardKey(agent.name), 0)), model=RANDOM_MODEL)

    model_names = [name for name in agent.models.keys() if name != true_model]

    for name in model_names:
        agent.resetBelief(model=name, ignore={modelKey(observer.name)})

    # observer has uniform prior distribution over possible agent models
    world.setMentalModel(observer.name, agent.name,
                         Distribution({name: 1. / (len(agent.models) - 1) for name in model_names}))

    # observer sees everything except true models
    observer.omega = [key for key in world.state.keys()
                      if key not in {modelKey(agent.name), modelKey(observer.name)}]  # rewardKey(agent.name),

    # generates trajectory
    logging.info('Generating trajectory of length {}...'.format(NUM_STEPS))
    trajectory = generate_trajectory(agent, NUM_STEPS)

    # gets evolution of inference over reward models of the agent
    probs = track_reward_model_inference(trajectory, model_names, agent, observer, [stateKey(agent.name, 'loc')])

    # create and save inference evolution plot
    plot_evolution(probs.T, [_get_fancy_name(name) for name in model_names],
                   'Evolution of Model Inference', None,
                   os.path.join(OUTPUT_DIR, 'inference.png'), 'Time', 'Model Probability', True)