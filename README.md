# raman-dp-id

Raman Spectroscopy Data Processing and Mineral Identification Tool, v1.1.0

# Overview

Raman DP-ID is a data-processing and mineral identification tool that serves two purposes:
- Streamline the Raman data **post-processing pipeline**
- Enable **automatic mineral identification** directly from Raman spectra

## Features

Raman DP-ID supports multiple data-processing features, including:
- spectrum cropping
- artifact removal
- automatic **baseline correction**
- manual baseline correction
- automatic **peak identification**

Raman DP-ID also implements several search algorithms to help identify the mineral(s) present in your sample using the peaks idenitifed in your spectra. Reference spectra come from [RRUFF](https://rruff.info/zipped_data_files/raman/) and have been labeled with peak positions. 

<table>
  <tr>
    <td>
        <img src="assets/baseline-estimated.png" alt="Screenshot of Raman DP-ID app showing automatic baseline estimate" width="200"/>
        <br>
        Automatic spectrum baseline estimate (screenshot of Raman DP-ID usage)
    </td>
    <td>
        <img src="assets/baseline-discretized.png" alt="Screenshot of Raman DP-ID app showing automatic baseline estimate after discretization, where points are now draggable" width="200"/>
        <br>
        Baseline estimate after discretization, where points are now draggable, and the baseline is editable
    </td>
  </tr>
</table>



# Setup (macOS)

- **Note: This program requires `python3.11+`**


## Automatic
- Download the [latest release](https://github.com/ariessunfeld/raman-spectroscopy/releases/download/raman-dp-id/raman-dp-id.zip) from GitHub
- Open Finder and unzip the latest release (by double-clicking the `.zip` file)
- **Right-click** `launcher.command`, click Open, then click Open again.
  - Note: If this does not open a new Terminal window automatically, open the Terminal, navigate to the folder containing `launcher.command`, execute `ls` to make sure you see that file, then run `chmod +x launcher.command` to give this file executable privileges. Then repeat this step.

## Manual
- Download the [latest release](https://github.com/ariessunfeld/raman-spectroscopy/releases/download/raman-dp-id/raman-dp-id.zip) from GitHub
- Open Finder and unzip the latest release (by double-clicking the `.zip` file)
- Open a new Terminal window at the folder
- Create a new virtual environment called `venv` by running `python3.11 -m venv venv`
- Activate the new virtual environment by running `source venv/bin/activate`
- Install the necessary packages into the virtual environment by running `pip install -r requirements.txt`
- Navigate into the latest version folder (e.g., `v1.2.3`) by running `cd v1.2.3` (replace with actual version number)
- Launch the program by running `python gui.py`

# Setup (Windows)

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


