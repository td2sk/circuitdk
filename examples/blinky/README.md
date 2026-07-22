# Blinky example

This example drives an LED from an ATtiny85 and demonstrates automatic KiCad library pin
resolution, a single `PB0` alias override, explicit unused pins, and assembly-specific footprint
assignment.

Run the example from this directory:

```console
circuitdk diff
circuitdk deploy
```

For example and test convenience, importing `circuit.py` creates a minimal empty
`hardware/blinky.kicad_sch` when it does not exist. Production projects should instead create and
save their schematic in KiCad before running CircuitDK.

After deployment, arrange and wire the symbols in KiCad, save and close the schematic, and run:

```console
circuitdk test
```
