import logging
import os
import random
from collections import OrderedDict

import numpy as np
from model_learning.util.plot import plot_bar

from psychsim.agent import Agent
from psychsim.world import World
from model_learning.metrics import evaluate_internal
from model_learning.planning import get_policy
from model_learning.algorithms.max_entropy import MaxEntRewardLearning, THETA_STR
from model_learning.trajectory import sample_sub_trajectories
from model_learning.util.io import get_file_name_without_extension, create_clear_dir, save_object, change_log_handler, \
    load_object
from atomic.parsing.replayer import Replayer
from atomic.definitions.map_utils import DEFAULT_MAPS
from atomic.definitions.plotting import plot, plot_trajectories, plot_agent_location_frequencies, \
    plot_agent_action_frequencies
from atomic.model_learning.linear.rewards import create_reward_vector
from atomic.model_learning.parser import TrajectoryParser

__author__ = 'Pedro Sequeira'
__email__ = 'pedrodbs@gmail.com'

# trajectory params
NUM_TRAJECTORIES = os.cpu_count()  # 8 # 20
TRAJ_LENGTH = 10  # 15
PRUNE_THRESHOLD = 5e-2  # 1e-2
SEED = 0

# learning algorithm params
HORIZON = 2
NORM_THETA = True
LEARNING_RATE = 0.5  # 1e-2
MAX_EPOCHS = 40  # 100  # 200
DIFF_THRESHOLD = 5e-3  # 1e-3

# data params
OUTPUT_DIR = 'output/linear-reward-learning'
PROCESSES = None
IMG_FORMAT = 'pdf'  # 'png'
TRAJECTORY_FILE_NAME = 'trajectory.pkl.gz'
RESULTS_FILE_NAME = 'result.pkl.gz'

AGENT_RATIONALITY = 1 / 0.1  # inverse temperature


class RewardModelAnalyzer(Replayer):
    """
    Replay analyzer that performs linear reward model learning given a player's data using the MaxEnt IRL algorithm.
    """
    parser_class = TrajectoryParser

    def __init__(self, replays, output=OUTPUT_DIR, maps=None, clear=True,
                 num_trajectories=NUM_TRAJECTORIES, length=TRAJ_LENGTH,
                 normalize=NORM_THETA, learn_rate=LEARNING_RATE, epochs=MAX_EPOCHS,
                 diff=DIFF_THRESHOLD, prune=PRUNE_THRESHOLD, horizon=HORIZON,
                 seed=0, verbosity=0, processes=PROCESSES, img_format=IMG_FORMAT):
        """
        Creates a new reward model learning replayer.
        :param list[str] replays: list of replay log files to process containing the player data.
        :param str output: path to the directory in which to save results.
        :param dict[str,dict[str,str]] maps: the map configuration dictionary.
        :param bool clear: whether to clear the output sub-directories.
        :param int num_trajectories: number of trajectories to use for reward learning.
        :param int length: length of the sub-trajectories used for reward learning.
        :param bool normalize: whether to normalize reward weights at each step of the algorithm.
        :param float learn_rate: the gradient descent learning/update rate.
        :param int epochs: the maximum number of gradient descent steps.
        :param float diff: the termination threshold for the weight vector difference.
        :param float prune: the likelihood below which stochastic outcomes are pruned.
        :param int horizon: planning horizon of the "learner" agent.
        :param int seed: seed for random number generation.
        :param int verbosity: verbosity level.
        :param int processes: the number of processes/cores to use. If `None`, all available cores will be used.
        :param str img_format: the format/extension of result images to be saved.
        """
        if maps is None:
            maps = DEFAULT_MAPS
        super().__init__(replays, maps, {})

        self_all_replays = replays
        self.output = output
        self.clear = clear
        self.num_trajectories = num_trajectories
        self.length = length
        self.normalize = normalize
        self.learn_rate = learn_rate
        self.epochs = epochs
        self.diff = diff
        self.prune = prune
        self.horizon = horizon
        self.seed = seed
        self.verbosity = verbosity
        self.processes = processes
        self.img_format = img_format

        self.results = {}
        self.trajectories = {}

    def process_files(self, num_steps=0, fname=None):
        # check results dir for each file, if results present, load them and don't reprocess
        files = []
        for file_name in self.files.copy():
            if not self._check_results(file_name):
                files.append(file_name)
        self.files = files

        if fname is None or fname in self.files:
            super().process_files(num_steps, fname)

    def _check_results(self, file_name):

        # checks already processed in this session
        if file_name in self.results and file_name in self.trajectories:
            return True

        # checks if results file exists and tries to load it
        output_dir = os.path.join(self.output, get_file_name_without_extension(file_name))
        results_file = os.path.join(output_dir, RESULTS_FILE_NAME)
        trajectory_file = os.path.join(output_dir, TRAJECTORY_FILE_NAME)
        if os.path.isfile(results_file) and os.path.exists(results_file) and \
                os.path.isfile(trajectory_file) and os.path.exists(trajectory_file):
            try:
                self.results[file_name] = load_object(results_file)
                logging.info('Loaded valid results from {}'.format(results_file))
                self.trajectories[file_name] = load_object(trajectory_file)
                logging.info('Loaded valid trajectory from {}'.format(trajectory_file))
                return True
            except:
                return False

    def post_replay(self, parser, world, agent, observer, map_table, victims, world_map):
        """
        Performs linear reward model learning using the Maximum Entropy IRL algorithm.
        :param atomic.model_learning.parser.TrajectoryParser parser: the trajectory parser with the collected player trajectory.
        :param dict map_table: a dictionary containing information on the environment map.
        :param World world: the PsychSim world.
        :param Agent agent: the player agent.
        :param Agent observer: the observer / ASIST agent.
        :param WorldMap world_map: the world map with location and move actions information.
        :param Victims victims: the info about victims distribution over the world.
        :return:
        """
        # checks result data, ignore if exists
        if self._check_results(parser.filename):
            return

        # checks trajectory
        trajectory = parser.trajectory
        if len(trajectory) <= self.length + self.num_trajectories - 1:
            logging.info('Could not process datapoint, empty or very short trajectory.')
            return

        # create output
        output_dir = os.path.join(self.output, get_file_name_without_extension(parser.filename))
        create_clear_dir(output_dir, self.clear)

        # sets up log to file
        change_log_handler(os.path.join(output_dir, 'learning.log'), self.verbosity)

        # sets general random seeds
        random.seed(self.seed)
        np.random.seed(self.seed)

        # print map
        neighbors = map_table['adjacency']
        locations = list(map_table['rooms'])
        coordinates = map_table['coordinates']
        plot(world, locations, neighbors, os.path.join(output_dir, 'env.{}'.format(self.img_format)), coordinates)

        logging.info('Parsed data file {} for player "{}" and got {} state-action pairs from {} events.'.format(
            parser.filename, parser.player_name(), len(trajectory), parser.data.shape[0]))
        plot_trajectories(agent, [trajectory], locations, neighbors,
                          os.path.join(output_dir, 'trajectory.{}'.format(self.img_format)), coordinates,
                          title='Player Trajectory')
        plot_agent_location_frequencies(
            agent, [trajectory], locations, os.path.join(output_dir, 'loc-frequencies.{}'.format(self.img_format)))
        plot_agent_action_frequencies(
            agent, [trajectory], os.path.join(output_dir, 'action-frequencies.{}'.format(self.img_format)))

        # collect sub-trajectories from player's trajectory
        trajectories = sample_sub_trajectories(trajectory, self.num_trajectories, self.length, seed=self.seed)
        logging.info('Collected {} trajectories of length {} from original trajectory.'.format(
            self.num_trajectories, self.length))
        plot_trajectories(agent, trajectories, locations, neighbors,
                          os.path.join(output_dir, 'sub-trajectories.{}'.format(self.img_format)), coordinates,
                          title='Training Sub-Trajectories')
        trajectories = [[(w.state, a) for w, a in t] for t in trajectories]

        # create reward vector and optimize reward weights via MaxEnt IRL
        logging.info('=================================')
        logging.info('Starting Maximum Entropy IRL optimization...')
        rwd_vector = create_reward_vector(agent, locations, world_map.moveActions[agent.name])
        alg = MaxEntRewardLearning(
            'max-ent', agent, rwd_vector, self.processes, self.normalize, self.learn_rate, self.epochs, self.diff, True,
            self.prune, self.horizon, self.seed)
        result = alg.learn(trajectories, parser.filename, self.verbosity > 0)

        # saves results/stats
        alg.save_results(result, output_dir, self.img_format)
        save_object(result, os.path.join(output_dir, RESULTS_FILE_NAME))
        self.results[parser.filename] = result
        save_object(trajectory, os.path.join(output_dir, TRAJECTORY_FILE_NAME))
        self.trajectories[parser.filename] = trajectory

        logging.info('=================================')

        # gets optimal reward function
        rwd_weights = result.stats[THETA_STR]
        rwd_vector.set_rewards(agent, rwd_weights)
        with np.printoptions(precision=2, suppress=True):
            logging.info('Optimized reward weights: {}'.format(rwd_weights))
        plot_bar(OrderedDict(zip(rwd_vector.names, rwd_weights)), 'Optimal Reward Weights ($θ$)',
                 os.path.join(output_dir, 'learner-theta.{}'.format(self.img_format)), plot_mean=False)
        learner_r = next(iter(agent.getReward().values()))
        logging.info('Optimized PsychSim reward function:\n\n{}'.format(learner_r))

        logging.info('=================================')

        # player's observed "policy"
        logging.info('Collecting observed player policy...')
        player_states = [w.state for w, _ in trajectory]
        player_pi = [a for _, a in trajectory]

        # compute learner's policy
        logging.info('Computing policy with learned reward for {} states...'.format(len(player_states)))
        agent.setAttribute('rationality', AGENT_RATIONALITY)
        learner_pi = get_policy(agent, player_states, None, self.horizon, 'distribution', self.prune, self.processes)

        logging.info('Computing evaluation metrics...')
        metrics = evaluate_internal(player_pi, learner_pi)
        logging.info('Results:')
        for name, metric in metrics.items():
            logging.info('\t{}: {:.3f}'.format(name, metric))

        logging.info('Finished processing {}!'.format(parser.filename))
        logging.info('=================================\n\n')