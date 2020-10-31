import logging
from model_learning.trajectory import copy_world
from atomic.parsing.parser import DataParser

__author__ = 'Pedro Sequeira'
__email__ = 'pedrodbs@gmail.com'


class TrajectoryParser(DataParser):
    def __init__(self, filename, maxDist=5, logger=logging):
        super().__init__(filename, maxDist, logger)
        self.trajectory = []
        self.prev_world = None
        self._player_name = None

    def pre_step(self, world):
        self.prev_world = copy_world(world)

    def post_step(self, world, act):
        if act is not None:
            self.trajectory.append((self.prev_world, act))

    def set_player_name(self, name):
        self._player_name = name

    def player_name(self):
        return super(TrajectoryParser, self).player_name() if self._player_name is None else self._player_name
