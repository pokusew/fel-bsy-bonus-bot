# bot

🚧 **Note:** This is a work-in-progress. The implementation is not finished yet. 🚧

A simple Python bot and a controller that uses [gist.github.com] for communication.

❗️ **Note:** This very simple bot was created purely for learning purposes as a solution of the "Black Gate" task from
the final Stage 5 of the Bonus Assignment from the [CTU FEE][ctu-fee] ([ČVUT FEL][cvut-fel])
[BSY course][ctu-fee-bsy] (Winter 2022/2023 term).


## Content

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Background](#background)
- [Implementation](#implementation)
- [Usage](#usage)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


## Background

The task's description from the CTFd:
> The final Stage 5 consists of only one task. You have to code a Python bot and a controller that
> uses [gist.github.com] for communication. See the attached [instructions.txt](./instructions.txt)
> file for the details.

See the [instructions.txt](./instructions.txt) for the details.


## Implementation

_Note: The implementation is more of a proof of a concept or demo. There are a lot of possible edge cases that we would
like to handle in real code._

The communication mechanism supports multiple bots (running on victims' machines) and one controller that is running on
the attacker's machine. Note that the controller does not have to be running all the time in order for the bots to be
working.

All messages between the controller and the bots are hidden in the images so that communication is not so suspicious.
We are using the same steganography technique that was used in Stage 3 (appending the zip-compressed data to the normal
image file).

Upon their startup, the controller and the bots download the memes library from
[this Gist](https://gist.github.com/pokusew/4c7fe7e6d06b0b90ab4848b234209e95). Note that this Gist is read-only
(neither the controller nor the bots have write access).

For the actual communication, another Gist is used. ID of that Gist together with the owner's GitHub
Personal access token (classic) with (at least) `gist` scope must be provided both
to the controller and to any bot via arguments (see [Usage](#usage) section).

Both the controller and the bots periodically (currently the period is set to 30 seconds) pull the latest changes from
the communication's Gist using `git`.

TODO finish implementation description


## Usage

TODO document


<!-- links references -->

[ctu-fee]: https://fel.cvut.cz/en

[cvut-fel]: https://fel.cvut.cz/cs

[ctu-fee-bsy]: https://cw.fel.cvut.cz/b221/courses/bsy/start

[gist.github.com]: https://gist.github.com/
