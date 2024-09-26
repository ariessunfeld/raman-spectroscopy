"""This module contains commands for handling spectrum manipulation

Each class (aside from CommandSpectrum and CommandHistory) derive from the Command
class. Each has an `undo` and an `execute` method. The commands are stored in the
GUI's `command_history` list. This structure enables Undo/Redo functionality in the GUI.
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore
from raman_dpid.utils import (
    get_smoothed_spectrum, 
    fit_gauss,
    gaussian
)


class Command:
    """Base class for Commands"""

    def execute(self):
        raise NotImplementedError

    def undo(self):
        raise NotImplementedError


class CommandSpectrum:
    """Represents a Spectrum for Command classes"""
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def copy(self):
        """Deep copy"""
        return CommandSpectrum(self.x.copy(), self.y.copy())

    def __iter__(self):
        return [self.x, self.y].__iter__()


class CommandHistory:
    """Container class for seuqnece of commands"""

    def __init__(self):
        self.commands = []
        self.index = -1

    def execute(self, command):
        """Disable further redoing after executing"""
        self.commands = self.commands[:self.index + 1]
        command.execute()
        self.commands.append(command)
        self.index += 1
    
    def undo(self):
        if self.index < 0:
            return
            # Add the "play" sound
        self.commands[self.index].undo()
        self.index -= 1

    def redo(self):
        if self.index == len(self.commands) - 1:
            return
            # Add the "play" sound
        self.index += 1
        self.commands[self.index].execute()


class LoadSpectrumCommand(Command):
    """Command to load a spectrum"""
    def __init__(self, app, xdata, ydata):
        self.app = app
        self.new_spectrum = CommandSpectrum(xdata, ydata)
        if self.app.spectrum is not None:
            self.old_spectrum = self.app.spectrum.copy()
        else:
            self.old_spectrum = None

        self.old_plot1_log = []

    def execute(self):
        # Backup plot log
        for idx in range(self.app.plot1_log.count()):
            line_to_back_up = self.app.plot1_log.item(idx).text()
            #print('backing up:', line_to_back_up)
            self.old_plot1_log.append(line_to_back_up)

        # Aesthetics
        self.app.plot1_log.clear()
        self.app.button_baseline.setText('Estimate Baseline')

        self.app.spectrum = self.new_spectrum
        if self.app.spectrum is not None:
            self.app.plot1.clear()
            self.app.plot1.plot(self.app.spectrum.x, self.app.spectrum.y)
            self.app.plot1.autoRange()

        # Communicate
        self.app.plot1_log.addItem(f"Loaded file: {str(self.app.unknown_spectrum_path)}")

    def undo(self):
        if self.old_plot1_log:
            self.app.plot1_log.clear()
            self.app.plot1_log.addItems(self.old_plot1_log)
        self.app.spectrum = self.old_spectrum
        if self.app.spectrum is not None:
            self.app.plot1.clear()
            self.app.plot1.plot(self.app.spectrum.x, self.app.spectrum.y)
            self.app.plot1.autoRange()
        else:
            self.app.plot1.clear()


class PointDragCommand(Command):
    """Command for moving a point on the baseline"""
    def __init__(self, app, index, startX, startY, endX, endY):
        self.app = app
        self.index = index
        self.startX = startX
        self.startY = startY
        self.endX = endX
        self.endY = endY

    def execute(self):
        self.app.draggableScatter.data['x'][self.index] = self.endX
        self.app.draggableScatter.data['y'][self.index] = self.endY
        self.app.update_discretized_baseline()
    
    def undo(self):
        self.app.draggableScatter.data['x'][self.index] = self.startX
        self.app.draggableScatter.data['y'][self.index] = self.startY
        self.app.update_discretized_baseline()


class EstimateBaselineCommand(Command):
    """This command stores the baseline estimate calculation and necessary GUI updates"""
    def __init__(self, app, estimated_baseline):
        self.app = app
        self.new_baseline = estimated_baseline
        if self.app.baseline_data is not None:
            self.old_baseline = self.app.baseline_data.copy()
        else:
            self.old_baseline = None

    def execute(self):

        # Aesthetics
        self.app.button_baseline.setText('Apply Baseline Correction')
        self.app.plot1_log.addItem('Baseline estimate calculated') # Communicate

        # Update data
        self.app.baseline_data = self.new_baseline
        
        # Update plot
        if self.app.baseline_plot is not None:
            self.app.plot1.removeItem(self.app.baseline_plot)
        self.app.baseline_plot = self.app.plot1.plot(self.app.spectrum.x, self.app.baseline_data, pen='r')
        
    def undo(self):
        # Aesthetics
        self.app.button_baseline.setText('Estimate Baseline') # TODO refactor with a toggle function

        self.app.baseline_data = self.old_baseline
        
        # Update the plot and baseline_data
        if self.app.baseline_plot is not None:
            self.app.plot1.removeItem(self.app.baseline_plot)
            self.app.baseline_data = None
        
        if self.app.baseline_data is not None:
            self.app.baseline_plot = self.app.plot1.plot(self.app.spectrum.x, self.app.baseline_data, pen='r')
        self.app.plot1_log.addItem("Baseline estimate undone")


class CorrectBaselineCommand(Command):
    """Command for subtracting the baseline estimate from the loaded spectrum"""
    def __init__(self, app):
        self.app = app

        # Store the old spectrum
        if self.app.spectrum is not None:
            self.old_spectrum = self.app.spectrum.copy()
        else:
            self.old_spectrum = None

        # Update the new spectrum
        if self.app.baseline_data is not None:
            self.new_spectrum = CommandSpectrum(self.app.spectrum.x, self.app.spectrum.y - self.app.baseline_data)
            self.old_baseline_data = self.app.baseline_data.copy()
        else:
            self.new_spectrum = CommandSpectrum(self.app.spectrum.x, self.app.spectrum.y)
            self.old_baseline_data = None
        
    def execute(self):
        # Aesthetics
        self.app.button_baseline.setText('Estimate Baseline')
        # Communicate
        self.app.plot1_log.addItem("Baseline corrected")
        
        self.app.spectrum = self.new_spectrum
        self.app.plot1.clear()
        self.app.plot1.plot(self.app.spectrum.x, self.app.spectrum.y)
        self.app.plot1.autoRange()

    def undo(self):
        # Aesthetics
        self.app.button_baseline.setText('Apply Baseline Correction')

        self.app.spectrum = self.old_spectrum
        self.app.baseline_data = self.old_baseline_data # Resture baseline data from before subtraction
        self.app.plot1.clear()
        if self.app.spectrum is not None:
            self.app.plot1.plot(self.app.spectrum.x, self.app.spectrum.y)
        if self.app.baseline_data is not None:
            self.app.baseline_plot = self.app.plot1.plot(self.app.spectrum.x, self.app.baseline_data, pen='r')
        self.app.plot1.autoRange()

        # Message
        self.app.plot1_log.addItem("Baseline restored")


class CropCommand(Command):
    def __init__(self, app, crop_start_x, crop_end_x):
        self.app = app
        self.crop_start_x = crop_start_x
        self.crop_end_x = crop_end_x
        
        # Back up app spectrum if not none        
        if self.app.spectrum is not None:
            self.old_spectrum = self.app.spectrum.copy()
        else:
            self.old_spectrum = None
        
        self.new_spectrum = self._get_cropped_spectrum()

    def _get_cropped_spectrum(self):
        indices_to_crop = np.where((self.old_spectrum.x >= self.crop_start_x) & (self.old_spectrum.x <= self.crop_end_x))
        new_y = self.old_spectrum.y.copy()
        new_y[indices_to_crop] = np.nan
        return CommandSpectrum(self.old_spectrum.x, new_y)

    def execute(self):
        self.app.spectrum = self.new_spectrum
        self.app.plot1.clear()
        self.app.plot1.plot(*self.app.spectrum)
        self.app.plot1_log.addItem(f'Cropped spectrum from {round(self.crop_start_x)} to {round(self.crop_end_x)} cm^-1')

    def undo(self):
        self.app.spectrum = self.old_spectrum
        self.app.plot1.clear()
        if self.app.spectrum is not None:
            self.app.plot1.plot(self.app.spectrum.x, self.app.spectrum.y)
            self.app.plot1_log.addItem(f'Undid crop from {round(self.crop_start_x)} to {round(self.crop_end_x)} cm^-1')


class SmoothCommand(Command):
    def __init__(self, app):
        self.app = app
        
        # Back up app spectrum if not none        
        if self.app.spectrum is not None:
            self.old_spectrum = self.app.spectrum.copy()
        else:
            self.old_spectrum = None
        
        self.new_spectrum = self._get_smoothed_spectrum()

    def _get_smoothed_spectrum(self):
        y = self.old_spectrum.y.copy()
        new_y = get_smoothed_spectrum(y)
        return CommandSpectrum(self.old_spectrum.x, new_y)

    def execute(self):
        self.app.spectrum = self.new_spectrum
        self.app.plot1.clear()
        self.app.plot1.plot(*self.app.spectrum)
        self.app.plot1_log.addItem(f'Smoothed spectrum')

    def undo(self):
        self.app.spectrum = self.old_spectrum
        self.app.plot1.clear()
        if self.app.spectrum is not None:
            self.app.plot1.plot(self.app.spectrum.x, self.app.spectrum.y)
            self.app.plot1_log.addItem(f'Undid spectrum smoothing')


class AddPeakPointCommand(Command):
    """TODO Implement peak point adding"""
    def __init__(self, app, x: float, y: float):
        self.app = app
        self.x = x
        self.y = y

    def execute(self):
        self.old_peaks_x = self.app.peaks_x.copy()
        self.old_peaks_y = self.app.peaks_y.copy()
        self.app.peaks_x = np.append(self.app.peaks_x, self.x)
        self.app.peaks_y = np.append(self.app.peaks_y, self.y)
        self.app.refresh_peaks_view()

    def undo(self):
        self.app.peaks_x = self.old_peaks_x.copy()
        self.app.peaks_y = self.old_peaks_y.copy()
        self.app.refresh_peaks_view()


class RemovePeakPointCommand(Command):
    """TODO Implement peak point removal"""
    def __init__(self, app, idx: int):
        self.app = app
        self.idx = idx

    def execute(self):
        self.old_peaks_x = self.app.peaks_x.copy()
        self.old_peaks_y = self.app.peaks_y.copy()
        self.app.peaks_x = np.delete(self.app.peaks_x, self.idx)
        self.app.peaks_y = np.delete(self.app.peaks_y, self.idx)
        self.app.refresh_peaks_view()

    def undo(self):
        self.app.peaks_x = self.old_peaks_x.copy()
        self.app.peaks_y = self.old_peaks_y.copy()
        self.app.refresh_peaks_view()


class FitPeaksCommand(Command):
    def __init__(self, app, peaks: list[float]):
        self.app = app
        self.peaks = peaks
        self.old_fit = self.app.fit
        self.old_fit_stats = self.app.fit_stats
        self.old_fit_trace = self.app.fit_trace
        self.old_component_fit_traces = self.app.fit_component_traces.copy()

    def execute(self):
        # Use the fitting logic to obtain the fit
        result, fit_stats = fit_gauss(self.app.spectrum.x, self.app.spectrum.y, self.peaks)
        
        self.new_fit = result.best_fit.copy()
        self.new_fit_stats = fit_stats
        self.new_fit_trace = pg.PlotDataItem(self.app.spectrum.x, self.new_fit, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine, width=2), name="Fitted Peaks")
        self.new_fit_component_traces = []
        
        # Write the fit params to the Fit Params part of the model
        self.app.fit_stats = self.new_fit_stats
        self.app.fit = self.new_fit
        self.app.fit_trace = self.new_fit_trace
        
        # Remove the old one if it's there
        if self.old_fit_trace is not None:
            self.app.plot1.removeItem(self.old_fit_trace)

        # Also remove old component traces
        if len(self.old_component_fit_traces) != 0:
            for tr in self.old_component_fit_traces:
                self.app.plot1.removeItem(tr)

        # Add the fit to the plot
        self.app.plot1.addItem(self.app.fit_trace)

        # Add the individual components of the fit
        # for prefix, component in result.model.components.items():
        #     if 'gaussian' in component.__class__.__name__.lower():
        #         component_trace = pg.PlotDataItem(
        #             self.app.spectrum.x, 
        #             result.eval_components()[prefix],
        #             pen=pg.mkPen('b', style=QtCore.Qt.PenStyle.DotLine, width=1))
        #         self.new_fit_component_traces.append(component_trace)
        #         self.app.plot1.addItem(component_trace)

        # Plot each individual Gaussian component
        components = result.eval_components(x=self.app.spectrum.x)
        for i, peak in enumerate(self.peaks):
            prefix = f'p{i}_'
            component_y = components[prefix]
            component_trace = pg.PlotDataItem(self.app.spectrum.x, component_y, pen=pg.mkPen('g', style=QtCore.Qt.PenStyle.DotLine, width=2))
            self.app.plot1.addItem(component_trace)
            self.new_fit_component_traces.append(component_trace)
    
        self.app.fit_component_traces = self.new_fit_component_traces.copy()

    def undo(self):

        # Revert fit params to old fit params
        self.app.fit = self.old_fit
        self.app.fit_stats = self.old_fit_stats
        self.app.fit_trace = self.old_fit_trace

        # Resolve plot
        self.app.plot1.removeItem(self.new_fit_trace)
        for tr in self.new_fit_component_traces:
            self.app.plot1.removeItem(tr)
        #if self.old_fit_trace is not None:
        #    self.app.plot1.addItem(self.old_fit_trace)


class FitPeaksCommand2(Command):
    def __init__(self, app, peaks: list[float]):
        self.app = app
        self.peaks = peaks
        self.old_fit_stats = self.app.fit_stats_2.copy() if self.app.fit_stats_2 is not None else None
        self.new_x = np.linspace(min(self.app.spectrum.x), max(self.app.spectrum.x), 10_000)

    def execute(self):

        result, fit_stats = fit_gauss(self.app.spectrum.x, self.app.spectrum.y, self.peaks)
        self.new_fit_stats = fit_stats
        self.app.fit_stats_2 = fit_stats
        new_x = np.linspace(min(self.app.spectrum.x), max(self.app.spectrum.x), 10_000)
        
        # Cleanup old curves
        for curve in self.app.gaussians:
            self.app.plot1.removeItem(curve)

        # Reset the list
        self.app.gaussians = []

        # Plot the new curves
        y_sum = np.zeros(new_x.shape)
        for peak, stats in fit_stats.items():
            y = gaussian(new_x, stats['Height'], stats['Center'], stats['Sigma'])
            y_sum += y
            self.app.gaussians.append(
                self.app.plot1.plot(new_x, y,
                    pen=pg.mkPen('g', width=2, style=QtCore.Qt.PenStyle.DashLine)
                ))
            
        # Cleanup old sum
        if self.app.gaussian_sum: 
            self.app.plot1.removeItem(self.app.gaussian_sum)

        # Plot the sum
        self.app.gaussian_sum = self.app.plot1.plot(new_x, y_sum, pen=pg.mkPen('m', width=2))

        # Remove existing control lines
        self.app.plot1.removeItem(self.app.peak_line)
        self.app.plot1.removeItem(self.app.center_line)
        self.app.plot1.removeItem(self.app.sigma_line)

        # Add the new control lines
        self.app.peak_line = pg.InfiniteLine(pos=fit_stats['Peak 1']['Height'], angle=0, movable=True, pen=pg.mkPen('r', width=2))
        self.app.center_line = pg.InfiniteLine(pos=fit_stats['Peak 1']['Center'], angle=90, movable=True, pen=pg.mkPen('b', width=2))
        self.app.sigma_line = pg.InfiniteLine(pos=fit_stats['Peak 1']['Center'] + fit_stats['Peak 1']['Sigma'], angle=90, movable=True, pen=pg.mkPen('g', width=2))

        # Set the update flag in the app
        self.app.updating_lines = False

        # Connect signals
        self.app.peak_line.sigPositionChanged.connect(self.app.update_gaussians)
        self.app.center_line.sigPositionChanged.connect(self.app.move_center)
        self.app.sigma_line.sigPositionChanged.connect(self.app.move_sigma)

        # Configure the dropdown
        self.app.dropdown_edit_peak.clear()
        self.app.dropdown_edit_peak.addItems(['Edit Peak: None Selected'])
        for i, (key, val) in enumerate(fit_stats.items()):
            label = f'Edit: {key} (~{round(val["Center"], 1)})'
            self.app.dropdown_edit_peak.addItem(label)
        #self.app.dropdown_edit_peak.addItems([f'Edit Peak: Peak {x+1}' for x in range(len(fit_stats))])
        self.app.dropdown_edit_peak.setEnabled(True)

    def undo(self):
        
        # revert to the old fit stats
        self.app.fit_stats_2 = self.old_fit_stats.copy() if self.old_fit_stats is not None else None

        # Cleanup old curves
        for curve in self.app.gaussians:
            self.app.plot1.removeItem(curve)

        # Cleanup old sum
        if self.app.gaussian_sum: 
            self.app.plot1.removeItem(self.app.gaussian_sum)

        # Reset the list
        self.app.gaussians = []

        # Plot the OLD curves
        if self.app.fit_stats_2 is not None:
            y_sum = np.zeros(self.new_x.shape)
            for peak, stats in self.app.fit_stats_2.items():
                y = gaussian(self.new_x, stats['Height'], stats['Center'], stats['Sigma'])
                y_sum += y
                self.app.gaussians.append(
                    self.app.plot1.plot(self.new_x, y,
                        pen=pg.mkPen('g', width=2, style=QtCore.Qt.PenStyle.DashLine)
                    ))

            # Plot the OLD sum
            self.app.gaussian_sum = self.app.plot1.plot(self.new_x, y_sum, pen=pg.mkPen('m', width=2))

        # Remove existing control lines
        self.app.plot1.removeItem(self.app.peak_line)
        self.app.plot1.removeItem(self.app.center_line)
        self.app.plot1.removeItem(self.app.sigma_line)

        # Add the new control lines
        if self.app.fit_stats_2 is not None:
            self.app.peak_line = pg.InfiniteLine(pos=self.app.fit_stats_2['Peak 1']['Height'], angle=0, movable=True, pen=pg.mkPen('r', width=2))
            self.app.center_line = pg.InfiniteLine(pos=self.app.fit_stats_2['Peak 1']['Center'], angle=90, movable=True, pen=pg.mkPen('b', width=2))
            self.app.sigma_line = pg.InfiniteLine(pos=self.app.fit_stats_2['Peak 1']['Center'] + self.app.fit_stats_2['Peak 1']['Sigma'], angle=90, movable=True, pen=pg.mkPen('g', width=2))

            # Connect signals
            self.app.peak_line.sigPositionChanged.connect(self.app.update_gaussians)
            self.app.center_line.sigPositionChanged.connect(self.app.move_center)
            self.app.sigma_line.sigPositionChanged.connect(self.app.move_sigma)
            
        # Set the update flag in the app
        self.app.updating_lines = False

        # Configure the dropdown
        self.app.dropdown_edit_peak.clear()
        self.app.dropdown_edit_peak.addItems(['Edit Peak: None Selected'])
        if self.app.fit_stats_2 is not None:
            for i, (key, val) in enumerate(self.app.fit_stats_2.items()):
                label = f'Edit: {key} (~{round(val["Center"], 1)})'
                self.app.dropdown_edit_peak.addItem(label)
            self.app.dropdown_edit_peak.setEnabled(True)
        