# Keithley Remote Control — I-V Measurement GUI

A PyQt5 desktop application for remote control of a Keithley source-measure unit (SMU) via GPIB/VISA, used for semiconductor device I-V characterization.

## Hardware Requirements

- **Keithley 2614B** (or compatible) dual-channel SMU
  - Channel A (smua): drain voltage source / current measurement
  - Channel B (smub): gate voltage source / current measurement
- **GPIB interface** (address `GPIB0::20::INSTR` by default; configurable in code)
- **NI-VISA** or **pyvisa-py** backend installed on the host PC

## Software Dependencies

| Package        | Version  | Purpose                        |
|---------------|----------|--------------------------------|
| Python         | ≥ 3.10   | Runtime                        |
| PyQt5          | ≥ 5.15   | GUI framework                  |
| pyqtgraph      | ≥ 0.13   | Real-time plotting             |
| pyvisa         | ≥ 1.13   | Instrument communication       |
| numpy          | ≥ 1.24   | Numerical arrays               |

Install with pip:

```bash
pip install PyQt5 pyqtgraph pyvisa numpy
```

> **Note:** You also need a VISA backend. Use `pip install pyvisa-py` for a pure-Python backend, or install NI-VISA from National Instruments for GPIB hardware support.

## UI File

Both scripts load a Qt Designer UI file named **`EL-TEST.ui`** at runtime. This file is **not included** in this repository. You must:

1. Create the UI in Qt Designer with the widget names referenced in the code (see table below), **or**
2. Rebuild the UI directly in Python using `loadUi()` or by replacing `loadUi('EL-TEST.ui', self)` with programmatic widget creation.

### Required Widget Names

| Widget              | Type          | Purpose                               |
|---------------------|---------------|---------------------------------------|
| `CurrentTime`       | `QWidget`     | Container for time-series plot        |
| `CurrentVD`         | `QWidget`     | Container for I-VD plot               |
| `CurrentVG`         | `QWidget`     | Container for I-VG plot               |
| `LogCurrentVD`      | `QWidget`     | Container for log I-VD plot           |
| `LogCurrentVG`      | `QWidget`     | Container for log I-VG plot           |
| `Start`             | `QPushButton` | Start measurement                     |
| `Stop`              | `QPushButton` | Stop measurement                      |
| `setVD`             | `QPushButton` | Apply drain voltage                   |
| `setVG`             | `QPushButton` | Apply gate voltage                    |
| `Sweep`             | `QPushButton` | Start VD sweep                        |
| `InputSetVD`        | `QTextEdit`   | VD setpoint input                     |
| `InputSetVG`        | `QTextEdit`   | VG setpoint input                     |
| `InputFirstVD`      | `QTextEdit`   | Sweep start voltage                   |
| `InputSecondVD`     | `QTextEdit`   | Sweep end voltage                     |
| `Step`              | `QTextEdit`   | Sweep step size                       |
| `WaitTime`          | `QTextEdit`   | Sweep wait time (seconds per step)    |
| `Display_VDsweep`   | `QLabel`      | Shows current VD during sweep         |
| `Progress`          | `QProgressBar`| Sweep progress bar                    |
| `OpenFolder`        | `QPushButton` | Open folder selection dialog          |
| `InputFolderName`   | `QTextEdit`   | Shows selected folder path            |
| `Save`              | `QPushButton` | Configure output file                 |
| `InputFileName`     | `QTextEdit`   | Output filename (without extension)   |

## Project Files

| File                   | Description                                                |
|------------------------|------------------------------------------------------------|
| `SweepVD.py`           | Original version — works but has known bugs (see below)    |
| `SweepVD_improved.py`  | **Recommended** — refactored with fixes and improvements   |

### Why Use the Improved Version?

The original `SweepVD.py` has several issues fixed in `SweepVD_improved.py`:

| Issue                                            | Fixed in improved |
|--------------------------------------------------|:-----------------:|
| State assignment bug (`==` instead of `=`)        | ✅ |
| `time.sleep(0.3)` blocks the GUI thread           | ✅ |
| Crash if file save path is not configured         | ✅ |
| `log10(0)` produces `-inf`, corrupting log plots   | ✅ |
| Duplicate `QTimer` and `time` imports             | ✅ |
| Global VISA connection fails at import time       | ✅ |
| Magic-number state machine (`0`/`0.5`/`1`)        | ✅ |
| No error handling for instrument I/O              | ✅ |
| No docstrings or type hints                       | ✅ |
| Resource leak — no cleanup on window close        | ✅ |

See the docstring at the top of `SweepVD_improved.py` for a detailed changelog.

## Usage

1. Connect the Keithley SMU to the PC via GPIB and power it on.
2. Ensure the GPIB address in the code matches your setup:
   ```python
   # KeithleySMU class in SweepVD_improved.py
   SOURCE_ADDRESS = "GPIB0::20::INSTR"
   ```
3. Run the application:
   ```bash
   python SweepVD_improved.py
   ```
4. In the GUI:
   - Set the output **folder** and **filename**, then click **Save**.
   - Click **Start** to begin real-time measurement.
   - Use **set VD** / **set VG** to apply fixed voltages.
   - Set **First VD**, **Second VD**, **Step**, and **Wait Time** for a drain-voltage sweep, then click **Sweep**.
   - Click **Stop** to end measurement (VD and VG must be at 0 V).

## Output File Format

Data is saved as CSV with the following columns:

```
Time[s], VD, VG, RealVD, RealVG, ID, IG, R2pp
```

- `VD`, `VG`: commanded setpoint voltages
- `RealVD`, `RealVG`: actual measured voltages
- `ID`, `IG`: measured drain and gate currents
- `R2pp`: calculated two-point resistance (`VD / ID`)

## Instrument Address Configuration

To change the GPIB address, edit the class constant in `SweepVD_improved.py`:

```python
class KeithleySMU:
    SOURCE_ADDRESS = "GPIB0::20::INSTR"   # ← change this
    CURRENT_LIMIT = 1e-4                  # ← compliance current, amps
```

## License

This project is for academic / laboratory use. No license specified.
