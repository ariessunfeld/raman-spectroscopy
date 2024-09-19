"""Utility functions for raman mineral identification"""

from itertools import combinations
import sqlite3
from datetime import datetime

from tqdm import tqdm
import pandas as pd
import numpy as np

from scipy.sparse import csc_matrix, eye, diags
from scipy.sparse.linalg import spsolve
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
from scipy.signal import savgol_filter

from pyspectra.readers.read_spc import read_spc

from lmfit.models import GaussianModel, LorentzianModel

import pyqtgraph as pg

def fetch_filename_and_peaks_filtered(database_path, peaks_set, tol):
    """Like filter_spectra_byinclusion but returns peaks as well"""
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    
    # Create the inclusion criteria for each peak in the set
    inclusion_conditions = []
    for peak in peaks_set:
        condition = "(strongest_peak >= ? AND strongest_peak <= ?)"
        inclusion_conditions.append((condition, peak - tol, peak + tol))
    
    # Build the SQL query
    query_conditions = " OR ".join([cond[0] for cond in inclusion_conditions])
    query_values = [val for cond in inclusion_conditions for val in cond[1:]]
    query = f"""
    SELECT filename, peaks
    FROM Spectra
    WHERE {query_conditions};
    """
    
    # Execute the SQL query
    cursor.execute(query, query_values)
    matching_rows = cursor.fetchall()
    
    conn.close()
    
    return matching_rows

def peaks_within_tolerance(known_peaks, unknown_peak, tol):
    """Check if the unknown peak is within tolerance of any of the known peaks."""
    for peak in known_peaks:
        if abs(peak - unknown_peak) <= tol:
            return True
    return False

def check_peak_superset(db_peaks, unknown_peaks, tol):
    """Check if db_peaks is a superset of unknown_peaks (within the given tolerance)."""
    for peak in unknown_peaks:
        if not peaks_within_tolerance(db_peaks, peak, tol):
            return False
    return True

def find_spectrum_matches(database_path, unknown_peaks, tol):
    """
    Find potential mineral combinations in the database that match the unknown spectrum.
    
    Parameters:
    - database_path: path to the SQLite database
    - unknown_peaks: list of peaks from the unknown spectrum
    - tol: the tolerance
    
    Returns:
    - List of combinations (filename sets) that match the unknown spectrum
    """
    
    rows = fetch_filename_and_peaks_filtered(database_path, unknown_peaks, tol)
    filenames = [row[0] for row in rows]
    db_peak_sets = [set(eval(row[1])) for row in rows]
    
    potential_matches = {1: [], 2: [], 3: []}
    
    # Check singles, pairs, and triples
    for r in range(1, 4):
        for combo_indices in tqdm(combinations(range(len(filenames)), r)):
            combined_peaks = set().union(*[db_peak_sets[i] for i in combo_indices])
            if check_peak_superset(combined_peaks, unknown_peaks, tol):
                potential_matches[r].append([filenames[i] for i in combo_indices])
    
    return potential_matches

def get_unique_mineral_combinations_optimized(database_path, combos):
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    
    # Fetch all filenames and their corresponding names from the Spectra table
    cursor.execute("SELECT filename, names FROM Spectra")
    filename_to_name = dict(cursor.fetchall())
    
    unique_combos = set()
    
    for combo in combos:
        # Lookup mineral names for the filenames in the combo using the in-memory dictionary
        names = [filename_to_name[filename] for filename in combo]
        names = tuple(sorted(names))
        unique_combos.add(names)
    
    conn.close()
    return unique_combos

def get_lines(file):
    with open(file, 'r') as f:
        lines = f.readlines()
    return lines

def axis_to_number(axis):
    if axis == 'x':
        return 0
    elif axis == 'y':
        return 1
    else:
        raise ValueError('Please enter x or y for `axis` parameter')

def get_data(file, axis='x'):
    # Extract data (x or y) from a .txt spectrum file

    n = axis_to_number(axis)
    
    data = []
    lines = get_lines(file)
    first_line = lines[0]
    if first_line.startswith('#'):
        for line in lines:
            if not line.startswith('##') and line.strip() and not line.startswith('800, -'):
                data += [float(line.split(', ')[n])]
        return data
    else: # Assume whitespace-separated
        for line in lines:
            line = line.strip()
            if line:
                data += [float(line.split()[n])]
        return data[::-1]


def get_xy_from_file(file):
    if file.name.lower().endswith('.txt'):
        try:
            x = get_data(file, axis='x')
            y = get_data(file, axis='y')
        except:
            raise ValueError(f'Could not extract x and y from {file}. Ensure format matches RRUFF .txt file format.')
        return np.array(x), np.array(y) / max(y)
    elif file.name.lower().endswith('.csv'):
        # TODO add error handling
        df = pd.read_csv(file)
        if 'x' in df.columns and 'y' in df.columns: # TODO Make this more flexible
            return np.array(df['x']), np.array(df['y']) / max(df['y'])
        else:
            raise ValueError('Cannot find columns x,y')
    elif file.name.lower().endswith('.spc'):
        spc = read_spc(file)
        df = spc.to_frame()
        df = df.reset_index()
        df.columns = ['x', 'y']
        retx = df['x'].to_list() 
        rety = df['y'].to_list()
        if retx[-1] < retx[0]:
            retx = retx[::-1]
            rety = rety[::-1]
        return np.array(retx), np.array(rety) / max(rety)
    
def deserialize(vec):
    return np.array(eval(vec))

def baseline_als(y, lam=1e5, p=0.05, niter=1000):
    L = len(y)
    valid_indices = ~np.isnan(y)
    y_valid = y[valid_indices]
    
    L_valid = len(y_valid)  # Length of valid y values
    D = diags([1, -2, 1], [0, -1, -2], shape=(L_valid, L_valid-2))
    D = lam * D.dot(D.transpose())
    w = np.ones(L_valid)
    W = diags([w], [0], shape=(L_valid, L_valid))
    
    for i in range(niter):
        W.setdiag(w)
        Z = W + D
        z_valid = spsolve(csc_matrix(Z), w*y_valid)
        w = p * (y_valid > z_valid) + (1-p) * (y_valid < z_valid)
    
    z = np.empty_like(y)
    z[:] = np.nan
    z[valid_indices] = z_valid
    return z

def get_peaks(x, y, width, rel_height, height, prominence):
    peaks, _ = find_peaks(y, width=width, rel_height=rel_height, height=height, prominence=prominence)
    return x[peaks], y[peaks]

def get_crop_index_suggestion(y: np.array):
    """Returns the index of the end of the suggested crop position
    
    Estimates a smooth second derivative of the spectrum and returns
    the index corresponding to the minimum value of the 2nd dertivative
    from within the first 50 points
    """
    dy = np.diff(y)
    smoothed_dy = gaussian_filter1d(dy, sigma=2)
    d2y = np.diff(smoothed_dy)
    return np.argmin(d2y[:55]) + 2  # two indices cut off by np.diff

def get_smoothed_spectrum(y: np.array, window_length: int=13, polyorder: int=3):
    return savgol_filter(y, window_length=window_length, polyorder=polyorder).copy()

def gaussian(x, A, mu, sigma):
    return A * np.exp(- (x - mu) ** 2 / (2 * sigma ** 2))

def fit_gauss(
        x: np.array, 
        y: np.array, 
        peaks: list[float], 
        Ltol: float=-2.0, 
        Rtol: float=2.0,
        min_sigma: float=0.1,
        max_nfev: int=10_000):
    
    model = None
    params = None

    y = np.nan_to_num(y, nan=0)

    for i, peak in enumerate(peaks):
        prefix = f'p{i}_'
        gauss = GaussianModel(prefix=prefix)
        if model is None:
            model = gauss
            params = gauss.make_params(
                center=peak, 
                amplitude=dict(value=max(y), min=0), 
                sigma=1
            )
        else:
            model += gauss
            params.update(
                gauss.make_params(
                    center=peak, 
                    amplitude=dict(value=max(y), min=0), 
                    sigma=1)
                )

        # Optionally, set parameter bounds (if you have prior knowledge)
        #params[prefix + 'center'].set(value=peak, min=peak+Ltol, max=peak+Rtol)
        #params[prefix + 'sigma'].set(min=min_sigma)

    # Fit the model to the datap
    result = model.fit(y, params, x=x, max_nfev=max_nfev)

    # Display the fitting report
    #print(result.fit_report())

    peak_stats = {}

    # Extract the peak parameters
    for i in range(len(peaks)):

        curr_peak = f'Peak {i+1}'
        peak_stats[curr_peak] = {}

        prefix = f'p{i}_'
        peak_area = result.params[prefix + 'amplitude'].value
        sigma = result.params[prefix + 'sigma'].value
        fwhm = result.params[prefix + 'sigma'].value * 2.35482  # FWHM for Gaussian
        peak_center = result.params[prefix + 'center'].value
        peak_height = result.params[prefix + 'height'].value

        peak_stats[curr_peak] |= dict(
            Center=peak_center, 
            Sigma=sigma,
            Area=peak_area, 
            FWHM=fwhm, 
            Height=peak_height
        )

    return result, peak_stats
