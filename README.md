# Overview

Raman data processing and mineral identification tool, v1.0.2

# Setup

- **Note: This program requires `python3.11+`**

## macOS

### Automatic
- Download the (latest release)[TODO] from GitHub
- Open Finder and unzip the latest release (by double-clicking the `.zip` file)
- Double-click `launcher.command`
  - Note: If this does not open a new Terminal window automatically, open the Terminal, navigate to the folder containing `launcher.command`, execute `ls` to make sure you see that file, then run `chmod +x launcher.command` to give this file executable privileges. Then repeat this step.

### Manual
- Download the (latest release)[TODO] from GitHub
- Open Finder and unzip the latest release (by double-clicking the `.zip` file)
- Open a new Terminal window at the folder
- Create a new virtual environment called `venv` by running `python3.11 -m venv venv`
- Activate the new virtual environment by running `source venv/bin/activate`
- Install the necessary packages into the virtual environment by running `pip install -r requirements.txt`
- Navigate into the latest version folder (e.g., `v1.2.3`) by running `cd v1.2.3` (replace with actual version number)
- Launch the program by running `python gui.py`

## Windows

- Coming soon!

# Usage

- Load a database (top left button; select the `raman_spectra_excellent_and_fair.db` file)
- Load a file for analysis (example file included: `ricolite-a_3a_10s_100p...`
- Enter peak detection parameters (recommended: `width=5`, `rel_height=0.5`, can increase `height` if necessary)
- Click Find Peaks button
- Enter a Tolerance (top right)
- Click Search
- Using the mineral names that appear, enter them into the box in the bottom right and click Search there
- Select a spectrum or spectra and press Plot
- Align X axis if necessary


