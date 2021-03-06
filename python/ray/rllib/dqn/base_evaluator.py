from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow as tf

import ray
from ray.rllib.dqn import models
from ray.rllib.dqn.common.wrappers import wrap_dqn
from ray.rllib.dqn.common.schedules import LinearSchedule
from ray.rllib.optimizers import SampleBatch, TFMultiGPUSupport


class DQNEvaluator(TFMultiGPUSupport):
    """The base DQN Evaluator that does not include the replay buffer."""

    def __init__(self, env_creator, config, logdir):
        env = env_creator()
        env = wrap_dqn(env, config["model"])
        self.env = env
        self.config = config

        tf_config = tf.ConfigProto(**config["tf_session_args"])
        self.sess = tf.Session(config=tf_config)
        self.dqn_graph = models.DQNGraph(env, config, logdir)

        # Create the schedule for exploration starting from 1.
        self.exploration = LinearSchedule(
            schedule_timesteps=int(
                config["exploration_fraction"] *
                config["schedule_max_timesteps"]),
            initial_p=1.0,
            final_p=config["exploration_final_eps"])

        # Initialize the parameters and copy them to the target network.
        self.sess.run(tf.global_variables_initializer())
        self.dqn_graph.update_target(self.sess)
        self.global_timestep = 0
        self.local_timestep = 0

        # Note that this encompasses both the Q and target network
        self.variables = ray.experimental.TensorFlowVariables(
            tf.group(self.dqn_graph.q_t, self.dqn_graph.q_tp1), self.sess)

        self.episode_rewards = [0.0]
        self.episode_lengths = [0.0]
        self.saved_mean_reward = None
        self.obs = self.env.reset()

    def set_global_timestep(self, global_timestep):
        self.global_timestep = global_timestep

    def update_target(self):
        self.dqn_graph.update_target(self.sess)

    def sample(self):
        obs, actions, rewards, new_obs, dones = [], [], [], [], []
        for _ in range(self.config["sample_batch_size"]):
            ob, act, rew, ob1, done = self._step(self.global_timestep)
            obs.append(ob)
            actions.append(act)
            rewards.append(rew)
            new_obs.append(ob1)
            dones.append(done)
        return SampleBatch({
            "obs": obs, "actions": actions, "rewards": rewards,
            "new_obs": new_obs, "dones": dones,
            "weights": np.ones_like(rewards)})

    def compute_gradients(self, samples):
        _, grad = self.dqn_graph.compute_gradients(
            self.sess, samples["obs"], samples["actions"], samples["rewards"],
            samples["new_obs"], samples["dones"], samples["weights"])
        return grad

    def apply_gradients(self, grads):
        self.dqn_graph.apply_gradients(self.sess, grads)

    def get_weights(self):
        return self.variables.get_weights()

    def set_weights(self, weights):
        self.variables.set_weights(weights)

    def tf_loss_inputs(self):
        return self.dqn_graph.loss_inputs

    def build_tf_loss(self, input_placeholders):
        return self.dqn_graph.build_loss(*input_placeholders)

    def _step(self, global_timestep):
        """Takes a single step, and returns the result of the step."""
        action = self.dqn_graph.act(
            self.sess, np.array(self.obs)[None],
            self.exploration.value(global_timestep))[0]
        new_obs, rew, done, _ = self.env.step(action)
        ret = (self.obs, action, rew, new_obs, float(done))
        self.obs = new_obs
        self.episode_rewards[-1] += rew
        self.episode_lengths[-1] += 1
        if done:
            self.obs = self.env.reset()
            self.episode_rewards.append(0.0)
            self.episode_lengths.append(0.0)
        self.local_timestep += 1
        return ret

    def stats(self):
        mean_100ep_reward = round(np.mean(self.episode_rewards[-101:-1]), 5)
        mean_100ep_length = round(np.mean(self.episode_lengths[-101:-1]), 5)
        exploration = self.exploration.value(self.global_timestep)
        return {
            "mean_100ep_reward": mean_100ep_reward,
            "mean_100ep_length": mean_100ep_length,
            "num_episodes": len(self.episode_rewards),
            "exploration": exploration,
            "local_timestep": self.local_timestep,
        }

    def save(self):
        return [
            self.exploration,
            self.episode_rewards,
            self.episode_lengths,
            self.saved_mean_reward,
            self.obs]

    def restore(self, data):
        self.exploration = data[0]
        self.episode_rewards = data[1]
        self.episode_lengths = data[2]
        self.saved_mean_reward = data[3]
        self.obs = data[4]
