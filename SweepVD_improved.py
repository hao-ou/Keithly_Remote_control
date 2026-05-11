"""
SweepVD — Keithley SMU I-V Measurement GUI (improved version)

A PyQt5 application for controlling a Keithley 2614B (or similar) source-measure unit
via GPIB/VISA to perform I-V characterization of semiconductor devices.

Original file: SweepVD.py
Changes in this version:
  - Fixed critical bug: `self.isStart == 0` → `self.isStart = 0` (line 301 of original)
  - Removed blocking `time.sleep(0.3)` from the GUI thread in update_plot()
  - Added None-check before file writes in update_plot() to prevent crashes
  - Safe log10: uses np.log10(max(abs(x), 1e-14)) to avoid -inf
  - Removed duplicate imports (QTimer, time)
  - Removed unused `sender` variables
  - Removed commented-out dead code
  - Moved VISA resource management into the class (no global side effects on import)
  - Used an IntEnum for application state instead of magic numbers 0/0.5/1
  - Added error handling for instrument I/O
  - Added docstrings and type hints
  - Instrument addresses are now class-level constants (easy to change)
"""

import sys
import os
import time
import numpy as np
from enum import IntEnum, auto

import pyvisa
import pyqtgraph as pg

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QMessageBox, QProgressBar, QFileDialog,
)
from PyQt5.QtCore import QTimer
from PyQt5.uic import loadUi
from PyQt5 import QtWidgets


# ---------------------------------------------------------------------------
# Application state  (replaces the fragile 0 / 0.5 / 1 magic numbers)
# ---------------------------------------------------------------------------
class AppState(IntEnum):
    STOPPED = 0      # idle, measurement not running
    READY = auto()   # measurement was stopped but can be restarted
    MEASURING = auto()  # timer is running, data is being acquired


# ---------------------------------------------------------------------------
# Instrument abstraction
# ---------------------------------------------------------------------------
class KeithleySMU:
    """Thin wrapper around a Keithley SMU accessed via pyvisa / GPIB."""

    # ---------- change these for your setup ----------
    SOURCE_ADDRESS = "GPIB0::20::INSTR"   # SMU A & B (2614B has two channels)
    CURRENT_LIMIT = 1e-4                  # compliance limit, amps
    # -------------------------------------------------

    def __init__(self) -> None:
        self._rm: pyvisa.ResourceManager | None = None
        self._instr: pyvisa.resources.MessageBasedResource | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open the VISA resource and configure the instrument."""
        self._rm = pyvisa.ResourceManager()
        self._instr = self._rm.open_resource(self.SOURCE_ADDRESS)
        self._instr.write("*CLS")
        self._instr.write(f"smua.source.limiti = {self.CURRENT_LIMIT}")
        self._instr.write(f"smub.source.limiti = {self.CURRENT_LIMIT}")

    def disconnect(self) -> None:
        """Close instrument and resource-manager handles gracefully."""
        if self._instr is not None:
            try:
                self._instr.close()
            except Exception:
                pass
            self._instr = None
        if self._rm is not None:
            try:
                self._rm.close()
            except Exception:
                pass
            self._rm = None

    @property
    def connected(self) -> bool:
        return self._instr is not None

    # ------------------------------------------------------------------
    # Voltage setting
    # ------------------------------------------------------------------
    def set_vd(self, voltage: float) -> None:
        """Set drain voltage on SMU channel A."""
        self._instr.write(f"smua.source.levelv={voltage:.2f}")

    def set_vg(self, voltage: float) -> None:
        """Set gate voltage on SMU channel B."""
        self._instr.write(f"smub.source.levelv={voltage:.2f}")

    # ------------------------------------------------------------------
    # Current / voltage reading
    # ------------------------------------------------------------------
    def read_id(self) -> float:
        """Read drain current (SMU channel A)."""
        return float(self._instr.query("print(smua.measure.i())"))

    def read_ig(self) -> float:
        """Read gate current (SMU channel B)."""
        return float(self._instr.query("print(smub.measure.i())"))

    def read_vd(self) -> float:
        """Read actual drain voltage (SMU channel A)."""
        return float(self._instr.query("print(smua.measure.v())"))

    def read_vg(self) -> float:
        """Read actual gate voltage (SMU channel B)."""
        return float(self._instr.query("print(smub.measure.v())"))


# ---------------------------------------------------------------------------
# Helper – safe base-10 log  (never returns -inf)
# ---------------------------------------------------------------------------
def safe_log10(value: float) -> float:
    """Return log10 of the absolute value, clamping near-zero inputs."""
    return float(np.log10(max(abs(value), 1e-14)))


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------
class MyApp(QMainWindow):
    """Main GUI window for Keithley SMU I-V measurement."""

    def __init__(self) -> None:
        super().__init__()
        loadUi("EL-TEST.ui", self)

        # -- Instrument --------------------------------------------------
        self.smu = KeithleySMU()

        # -- UI widget lookups -------------------------------------------
        self.container_CurrentTime = self.findChild(QWidget, "CurrentTime")
        self.container_CurrentVD = self.findChild(QWidget, "CurrentVD")
        self.container_CurrentVG = self.findChild(QWidget, "CurrentVG")
        self.container_LogCurrentVD = self.findChild(QWidget, "LogCurrentVD")
        self.container_LogCurrentVG = self.findChild(QWidget, "LogCurrentVG")

        self.start = self.findChild(QWidget, "Start")
        self.stop = self.findChild(QWidget, "Stop")
        self.setvd = self.findChild(QWidget, "setVD")
        self.setvg = self.findChild(QWidget, "setVG")
        self.sweep = self.findChild(QWidget, "Sweep")
        self.changeVD = self.findChild(QWidget, "InputSetVD")
        self.changeVG = self.findChild(QWidget, "InputSetVG")
        self.FirstVD = self.findChild(QWidget, "InputFirstVD")
        self.SecondVD = self.findChild(QWidget, "InputSecondVD")
        self.Step = self.findChild(QWidget, "Step")
        self.Wait = self.findChild(QWidget, "WaitTime")
        self.display_VD = self.findChild(QLabel, "Display_VDsweep")
        self.progress = self.findChild(QProgressBar, "Progress")

        self.OpenFolder = self.findChild(QWidget, "OpenFolder")
        self.FolderName = self.findChild(QWidget, "InputFolderName")
        self.SaveFile = self.findChild(QWidget, "Save")
        self.FileName = self.findChild(QWidget, "InputFileName")

        # -- Plot widgets ------------------------------------------------
        self.plot_CurrentTime = pg.PlotWidget(self.container_CurrentTime)
        self.plot_CurrentVD = pg.PlotWidget(self.container_CurrentVD)
        self.plot_CurrentVG = pg.PlotWidget(self.container_CurrentVG)
        self.plot_LogCurrentVD = pg.PlotWidget(self.container_LogCurrentVD)
        self.plot_LogCurrentVG = pg.PlotWidget(self.container_LogCurrentVG)

        # Ensure each container has a layout
        for container in (
            self.container_CurrentTime,
            self.container_CurrentVD,
            self.container_CurrentVG,
            self.container_LogCurrentVD,
            self.container_LogCurrentVG,
        ):
            if not container.layout():
                container.setLayout(QVBoxLayout())

        # Add plot widgets to layouts
        self.container_CurrentTime.layout().addWidget(self.plot_CurrentTime)
        self.container_CurrentVD.layout().addWidget(self.plot_CurrentVD)
        self.container_CurrentVG.layout().addWidget(self.plot_CurrentVG)
        self.container_LogCurrentVD.layout().addWidget(self.plot_LogCurrentVD)
        self.container_LogCurrentVG.layout().addWidget(self.plot_LogCurrentVG)

        # Legends
        for plot in (
            self.plot_CurrentTime,
            self.plot_CurrentVD,
            self.plot_CurrentVG,
            self.plot_LogCurrentVD,
            self.plot_LogCurrentVG,
        ):
            plot.addLegend()

        # -- Button connections ------------------------------------------
        self.isStart = AppState.STOPPED
        self.start.setCheckable(True)
        self.start.clicked.connect(self.clickStart)
        self.stop.clicked.connect(self.clickStop)
        self.setvd.clicked.connect(self.Set_VD)
        self.setvg.clicked.connect(self.Set_VG)
        self.isSweeping = False
        self.Sweep.clicked.connect(self.StartSweep)
        self.OpenFolder.clicked.connect(self.SelectFolder)
        self.SaveFile.clicked.connect(self.SaveTxt)

        self.timetick = 0

        # -- Initial voltage state ---------------------------------------
        # Start at 0 V on both channels; instrument will be connected on first Start
        self.current_vd = 0.0
        self.current_vg = 0.0

        # -- Data buffers ------------------------------------------------
        self.timeint = 10                    # timer interval, ms
        self.x_data: list[int] = [0]

        # Pre-fill with a safe placeholder so plots don't crash before first reading
        self.id_data: list[float] = [0.0]
        self.logid_data: list[float] = [safe_log10(1e-14)]
        self.ig_data: list[float] = [0.0]
        self.logig_data: list[float] = [safe_log10(1e-14)]

        self.vd_record: list[float] = [self.current_vd]
        self.vg_record: list[float] = [self.current_vg]
        self.real_vd_data: list[float] = [0.0]
        self.real_vg_data: list[float] = [0.0]

        # File path (set by SaveTxt)
        self.fpath: str | None = None

        # Sweep timer
        self.timer2: QTimer | None = None

        # -- Post-init cleanup -------------------------------------------
        self.progress.reset()

    # ==================================================================
    #  Data acquisition (called by QTimer)
    # ==================================================================

    def update_plot(self) -> None:
        """Read one data point from the instrument and refresh the time plot.

        Called periodically by the measurement timer.
        """
        # ---- Read instrument ----
        x = self.x_data[-1] + 1
        this_id = self.smu.read_id()
        this_logid = safe_log10(this_id)
        this_ig = self.smu.read_ig()
        this_logig = safe_log10(this_ig)
        real_vd = self.smu.read_vd()
        real_vg = self.smu.read_vg()

        # ---- Store ----
        self.x_data.append(x)
        self.id_data.append(this_id)
        self.logid_data.append(this_logid)
        self.ig_data.append(this_ig)
        self.logig_data.append(this_logig)
        self.real_vd_data.append(real_vd)
        self.real_vg_data.append(real_vg)

        # ---- Plot time traces ----
        time_axis = np.array(self.x_data) * self.timeint / 1000.0
        self.plot_CurrentTime.plot(
            time_axis, self.id_data, pen="r", clear=True, name="ID"
        )
        self.plot_CurrentTime.plot(
            time_axis, self.ig_data, pen="w", name="IG"
        )

        # ---- Write to file (if a file has been configured) ----
        self._append_data_to_file()

    # ------------------------------------------------------------------
    def voltagevessel(self) -> None:
        """Record current Vd/Vg setpoints and refresh the I-V scatter plots.

        Called periodically by the measurement timer (together with update_plot).
        """
        self.vd_record.append(self.current_vd)
        self.vg_record.append(self.current_vg)
        self.Display_VDsweep.setText(str(round(self.current_vd, 4)))

        self.plot_CurrentVD.plot(
            self.vd_record, self.id_data, pen="r", clear=True, name="ID"
        )
        self.plot_CurrentVD.plot(
            self.vd_record, self.ig_data, pen="w", name="IG"
        )

        self.plot_CurrentVG.plot(
            self.vg_record, self.id_data, pen="r", clear=True, name="ID"
        )
        self.plot_CurrentVG.plot(
            self.vg_record, self.ig_data, pen="w", name="IG"
        )

    # ------------------------------------------------------------------
    def _append_data_to_file(self) -> None:
        """Append the most recent data row to the open output file (if any)."""
        if self.fpath is None:
            return

        try:
            time_sec = self.x_data[-2] / 10.0 if len(self.x_data) >= 2 else 0.0
            r2pp = self.current_vd / (self.id_data[-1] + 1e-14)
            with open(self.fpath, "a") as f:
                f.write(
                    f"{time_sec},"
                    f"{self.current_vd},"
                    f"{self.current_vg},"
                    f"{self.real_vd_data[-1]},"
                    f"{self.real_vg_data[-1]},"
                    f"{self.id_data[-1]},"
                    f"{self.ig_data[-1]},"
                    f"{r2pp}\n"
                )
        except OSError as exc:
            print(f"[WARNING] Failed to write data to file: {exc}")

    # ==================================================================
    #  Button handlers
    # ==================================================================

    def clickStart(self) -> None:
        """Start (or resume) real-time measurement."""
        # Connect to instrument if not already connected
        if not self.smu.connected:
            try:
                self.smu.connect()
                self.smu.set_vd(self.current_vd)
                self.smu.set_vg(self.current_vg)
            except Exception as exc:
                self.show_warning_popup("Connection Error", str(exc))
                return

        self.smu._instr.write("*CLS")

        if self.isStart == AppState.STOPPED:
            self._begin_measurement()

        elif self.isStart == AppState.READY:
            if self.fpath and os.path.exists(self.fpath):
                choice = self.show_file_warning_popup(
                    "Warning",
                    "This file already exists\nDo you want to overwrite it?",
                )
                if choice == QMessageBox.Yes:
                    os.remove(self.fpath)
                    open(self.fpath, "a").close()
                    self._reset_data_buffers()
                    self._begin_measurement()
                else:
                    # Remain in READY state  (fixed: was == 0 which is a comparison)
                    self.isStart = AppState.READY
            else:
                self._reset_data_buffers()
                self._begin_measurement()

    # ------------------------------------------------------------------
    def _begin_measurement(self) -> None:
        """Internal helper: start the measurement timer."""
        self.start.setText("Measuring")
        self.isStart = AppState.MEASURING
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_plot)
        self.timer.timeout.connect(self.voltagevessel)
        self.timer.start(self.timeint)
        self.plot_CurrentTime.showGrid(True, True)

    # ------------------------------------------------------------------
    def _reset_data_buffers(self) -> None:
        """Clear all accumulated data buffers for a fresh measurement run."""
        self.x_data = [0]
        self.id_data = [self.smu.read_id() if self.smu.connected else 0.0]
        self.logid_data = [safe_log10(self.id_data[0])]
        self.ig_data = [self.smu.read_ig() if self.smu.connected else 0.0]
        self.logig_data = [safe_log10(self.ig_data[0])]
        self.vd_record = [0.0]
        self.vg_record = [0.0]

    # ------------------------------------------------------------------
    def clickStop(self) -> None:
        """Stop measurement.  Requires VD = VG = 0 for safety."""
        if self.isStart != AppState.MEASURING:
            return

        if self.current_vd == 0 and self.current_vg == 0:
            self.start.setText("Start")
            self.start.setChecked(False)
            self.timer.stop()
            self.isStart = AppState.READY
            self.progress.reset()
            self.Sweep.setText("Go!")

            # Disconnect instrument cleanly
            self.smu.disconnect()
        else:
            self.show_warning_popup("Warning", "Set VD and VG to zero before stopping!")

    # ------------------------------------------------------------------
    def Set_VD(self) -> None:
        """Apply the drain voltage entered in the UI to the instrument."""
        if not self.smu.connected:
            return

        if self.isStart in (AppState.MEASURING, AppState.READY) and not self.isSweeping:
            try:
                num = float(self.changeVD.toPlainText())
            except ValueError:
                self.show_warning_popup("Input Error", "VD must be a number.")
                return
            self.current_vd = num
            self.smu.set_vd(self.current_vd)

    # ------------------------------------------------------------------
    def Set_VG(self) -> None:
        """Apply the gate voltage entered in the UI to the instrument."""
        if not self.smu.connected:
            return

        if self.isStart in (AppState.MEASURING, AppState.READY) and not self.isSweeping:
            try:
                num = float(self.changeVG.toPlainText())
            except ValueError:
                self.show_warning_popup("Input Error", "VG must be a number.")
                return
            self.current_vg = num
            self.smu.set_vg(self.current_vg)

    # ------------------------------------------------------------------
    def StartSweep(self) -> None:
        """Start a drain-voltage sweep between two endpoints."""
        if self.isStart not in (AppState.MEASURING, AppState.READY):
            return

        try:
            self.firstVD = float(self.FirstVD.toPlainText())
            self.secondVD = float(self.SecondVD.toPlainText())
            self.step = float(self.Step.toPlainText())
            self.wait = float(self.WaitTime.toPlainText())
        except ValueError:
            self.show_warning_popup("Input Error", "Sweep parameters must be numbers.")
            return

        # Sweep is only allowed when VD is at 0 V and the endpoints straddle zero
        if self.current_vd == 0 and self.firstVD * self.secondVD < 0:
            self.isSweeping = True
            self.Sweep.setText("Working")

            # Build sweep path:  0 → firstVD → secondVD → 0
            path1 = np.arange(0, self.firstVD + self.step, self.step)
            path2 = np.arange(self.firstVD, self.secondVD - self.step, -self.step)
            path3 = np.arange(self.secondVD, 0 + self.step, self.step)
            self.path = np.hstack((path1, path2, path3))

            self.progress.reset()
            self.progress.setRange(0, self.path.shape[0])

            self.timer2 = QTimer(self)
            self.timer2.timeout.connect(self.SweepVD)
            self.timer2.start(int(1000 * self.wait))

    # ------------------------------------------------------------------
    def SweepVD(self) -> None:
        """Advance the sweep by one step (called by the sweep timer)."""
        self.progress.setValue(self.timetick + 1)
        self.current_vd = self.path[self.timetick]
        self.smu.set_vd(self.current_vd)
        self.timetick += 1

        if self.timetick >= self.path.shape[0]:
            self.timer2.stop()
            self.current_vd = 0.0
            self.smu.set_vd(0.0)
            self.isSweeping = False
            self.Sweep.setText("Sweep")
            self.timetick = 0

    # ==================================================================
    #  File I/O
    # ==================================================================

    def SelectFolder(self) -> None:
        """Open a folder selection dialog."""
        self.filefolder = QFileDialog.getExistingDirectory(
            self, "Select Directory", "./"
        )
        self.FolderName.setText(self.filefolder)

    # ------------------------------------------------------------------
    def SaveTxt(self) -> None:
        """Configure the output file for data logging."""
        if self.isStart in (AppState.STOPPED, AppState.READY):
            self.fname = self.FileName.toPlainText()
            self.fpath = os.path.join(
                self.filefolder if hasattr(self, "filefolder") else ".",
                f"{self.fname}.txt",
            )

            if os.path.exists(self.fpath):
                choice = self.show_file_warning_popup(
                    "Warning",
                    "This file already exists\nDo you want to overwrite it?",
                )
                if choice == QMessageBox.No:
                    self.fpath = None
                    return
                os.remove(self.fpath)

            # Write header
            with open(self.fpath, "a") as f:
                f.write("Time[s],VD,VG,RealVD,RealVG,ID,IG,R2pp\n")

    # ==================================================================
    #  Dialogs
    # ==================================================================

    @staticmethod
    def show_warning_popup(title: str, text: str) -> None:
        """Display a warning message box."""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.exec_()

    @staticmethod
    def show_file_warning_popup(title: str, text: str):
        """Display a Yes/No message box and return the user's choice."""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        return msg_box.exec_()

    # ==================================================================
    #  Cleanup
    # ==================================================================

    def closeEvent(self, event) -> None:
        """Ensure the instrument connection is closed when the window is closed."""
        self.smu.disconnect()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MyApp()
    window.show()
    sys.exit(app.exec_())
