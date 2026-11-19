# Chess Grind — Pinokio Windows beta

A local-first chess training studio with Stockfish 19, opening and endgame lessons, historical master games, local practice, and optional Chess.com public-game import.

## Install

Requires **Windows x64** and a current Pinokio installation with Python support. In Pinokio, select **Download from URL** and enter this repository's published URL (when available). Select **Install Chess Grind**, then **Start Chess Grind**, and open the local URL. Pinokio downloads dependencies and the official Stockfish engine during installation.

## Your own Chess.com account

A clean install has **no connected account**. Open **Settings** in Chess Grind and enter **your own Chess.com username** or public member URL. Confirm the profile and explicitly enable import. The app does not ask for a Chess.com password. No developer game history or profile is included.

## Data, updates and limits

Data and progress live under `userdata/` inside your installation and are not distributed. **Back up `userdata/` before changing installations.** The Pinokio Update action uses a fast-forward git pull and reruns dependency/bootstrap setup without intentionally deleting user records. The local server binds to `127.0.0.1`; remote multiplayer is not offered. Initial installation and Chess.com import need an internet connection. Ollama is optional and is not installed automatically. The beta is presently tested for Windows x64 only.

Historical PGNs: PGN Mentor; ECO data: Lichess chess-openings (CC0); Stockfish: official GPLv3 project. Independent project, not affiliated with Chess.com, Lichess, Pinokio, or Stockfish.

Screenshots and announcement drafts: `marketing/`. This repository is a release candidate until an isolated Pinokio clean install is verified.
