# Python APIリファレンス

[English](api-reference.md) | [日本語](api-reference.ja.md)

CircuitDK alpha版のPython APIを簡潔にまとめた資料です。別のmoduleを明記していない型は、
`circuitdk`からimportできます。

## 最小構成

ユーザーmoduleでは、1つの`Circuit`を作り、その下に部品とnetを定義して、CLIのentrypointに
なる`KicadProject`をmodule-levelで公開します。

```python
from circuitdk import Circuit, KicadProject, Part, V, kohm

circuit = Circuit("Blinky")
vdd = circuit.power("VDD", voltage=5 * V)
gnd = circuit.ground("GND")

power = Part(
    circuit,
    "PowerInput",
    symbol="Connector_Generic:Conn_01x02",
    pin_overrides={"VDD": "1", "GND": "2"},
)
resistor = Part(circuit, "LedResistor", symbol="Device:R", value=1 * kohm)
led = Part(circuit, "Led", symbol="Device:LED")

vdd.connect(power.pin("VDD"), resistor.pin("1"))
circuit.connect(resistor.pin("2"), led.pin("A"))
gnd.connect(led.pin("K"), power.pin("GND"))

project = KicadProject(circuit, "hardware/blinky.kicad_sch")
```

`circuitdk.toml`から、module-levelの`project` objectを指定します。

```toml
[project]
entrypoint = "circuit:project"
state_directory = ".circuitdk"
```

通常の流れは、`circuitdk diff`、`circuitdk deploy`、KiCadでの配置・配線、
`circuitdk test`です。

## IDと所有範囲

各objectには、scopeとconstruct IDから安定したpathが割り当てられます。

```python
circuit = Circuit("Board")
led = Part(circuit, "StatusLed", symbol="Device:LED")

assert led.path == "/Board/StatusLed"
```

このpathをCircuitDK IDとして使用します。`R1`のように変更され得るKiCad referenceを論理IDに
使用しないでください。管理対象部品の存在とfieldはPythonが所有し、配置、回転、wire、label、
見た目はKiCadが所有します。

## 基本の型

### `Construct`

Construct treeに含まれるobjectの基底classです。

| Member | 意味 |
| --- | --- |
| `scope` | 親construct。root circuitでは`None`。 |
| `construct_id` | 親scope内で一意のID。`/`は使用不可。 |
| `path` | Construct treeから生成される安定した絶対論理ID。 |
| `circuit` | このconstructを含むroot `Circuit`。 |

アプリケーション固有の再利用可能な回路は`Construct`を継承し、`__init__`内で子部品、net、
別のconstructを作成して実装できます。

### `Circuit`

```python
Circuit(construct_id: str)
```

Root constructであり、mutableな回路builderです。

| Method | 用途 |
| --- | --- |
| `net(id)` | 名前付きsignal `Net`を作成する。 |
| `power(id, voltage=None)` | 名前付きpower `Net`を作成する。 |
| `ground(id="GND")` | Ground `Net`を作成する。 |
| `connect(*pins)` | 2つ以上のpinをanonymous netで接続する。 |
| `no_connect(pin)` | 意図的な未接続pinとして指定する。通常は`pin.no_connect()`を使用する。 |
| `synth()` | Immutableな`CircuitIR`を生成する。通常はCLIが`KicadProject`経由で呼び出す。 |

作成した`Part`や`Net`は通常のPython変数で保持してください。Alpha APIにはglobalな公開
`Parts` collectionはありません。

### `Part`

```python
Part(
    scope,
    construct_id,
    *,
    symbol,
    pins=None,
    pin_overrides=None,
    value=None,
    footprint=None,
    in_bom=True,
    on_board=True,
    dnp=False,
)
```

| Argument・属性 | 意味 |
| --- | --- |
| `symbol` | `Device:R`などのKiCad library ID。必須。 |
| `value` | コード管理の値。省略時はsymbol名。`Quantity`はKiCadへのserialization境界まで数値として保持し、明示した`str`は変更しない。 |
| `footprint` | KiCad footprint library IDまたは`None`。BOM dataから後で代入可能。 |
| `in_bom` | BOMへ含めるか。 |
| `on_board` | PCB transferの対象にするか。 |
| `dnp` | Do-not-populate状態。 |
| `pin(name_or_number)` | 解決済みの名前、alias、番号から`Pin`を取得する。 |

デフォルトでは、選択したKiCad symbol libraryからすべてのpinを解決します。Library上の名前と
異なる、コード向けの分かりやすいaliasが必要な場合だけ`pin_overrides`を使用します。

```python
mcu = Part(
    circuit,
    "Mcu",
    symbol="MCU_Microchip_ATtiny:ATtiny85-20P",
    pin_overrides={"PB0": "5"},  # KiCad上の名前はAREF/PB0。
)
```

生成されたlibraryや利用できないlibraryには`pins={"name": "number"}`を使用します。`pins`は
完全なpin集合を定義し、その部品のKiCad library pin解決を無効にします。`pins`と
`pin_overrides`は同時に指定できません。

### `Pin`

| Member | 意味 |
| --- | --- |
| `part` | このpinを所有する`Part`。 |
| `name` | 解決済みの名前またはコード向けalias。 |
| `number` | 物理symbol pin番号。 |
| `ref` | Circuit IRが使用するimmutableな`PinRef`。 |
| `no_connect()` | 意図的な未接続pinに指定し、そのpin自身を返す。 |

厳密なtestを実行する前に、解決されたすべてのpinを接続するか、no-connectとして明示して
ください。

### `Net`

| Member | 意味 |
| --- | --- |
| `kind` | `signal`、`power`、`ground`のいずれか。 |
| `voltage` | Power netでは文字列へ正規化した電圧。それ以外は`None`。 |
| `connect(*pins)` | Pinをnetへ追加し、同じ`Net`を返す。 |

同じnetへ再度`connect()`すると、論理netへpinを追加できます。

```python
vdd.connect(controller.pin("VCC"))
vdd.connect(sensor.pin("VDD"), capacitor.pin1)
```

## Passive部品

### `Resistor`、`Capacitor`、`Inductor`

```python
Resistor(scope, id, *, resistance, footprint=None)
Capacitor(scope, id, *, capacitance, footprint=None)
Inductor(scope, id, *, inductance, footprint=None)
```

いずれも`pin1`と`pin2`を公開します。数値を`.resistance`、`.capacitance`、
`.inductance`として保持し、対応する`Device:R`、`Device:C`、`Device:L` symbolを設定します。

`circuitdk.parts`からimportします。

## Experimentalな回路pattern

```python
from circuitdk.experimental.patterns import (
    LedIndicator,
    VoltageDivider,
    decouple,
    pull_down,
    pull_up,
)
```

これらは設計中のAPIであり、patch releaseでも予告なく変更・削除される可能性があります。
Pullとdecoupling helperは明示的に作成した部品を受け取り、通常の接続だけを追加します。

```python
pull_down(*, signal, resistor, ground)
pull_up(*, signal, resistor, power)
decouple(*, power_pin, capacitor, ground)
```

### `LedIndicator`

```python
LedIndicator(
    scope,
    id,
    *,
    drive,
    return_to,
    series_resistance,
    led_footprint=None,
    resistor_footprint=None,
)
```

`.resistor`と`.led`を作成して直列に接続します。

### `VoltageDivider`

```python
VoltageDivider(
    scope,
    id,
    *,
    input_net,
    return_to,
    upper_resistance,
    lower_resistance,
    footprint=None,
)
```

`.upper`、`.lower`と、分圧出力の`.output` netを公開します。

## Protocol接続

SPI、I2C、UART接続は`circuitdk.protocols`から利用できます。

```python
from circuitdk.protocols import I2C, SPI, UART, pin_override
```

各signalのpinは、controllerやdeviceを基準に名前または番号で指定できます。別途取得した
`Pin`を直接渡すこともできます。

### `SPI`

```python
spi = SPI(
    scope,
    id,
    controller=controller,
    sck="SPI_SCK",
    mosi="SPI_MOSI",
    miso="SPI_MISO",
)
spi.add_peripheral(
    device=sensor,
    sck="SCLK",
    sdi="SDI",
    sdo="SDO",
    controller_cs="SENSOR_CS",
    device_cs="NCS",
)
```

controller側では`mosi`/`sdo`と`miso`/`sdi`、peripheral側では`sdi`/`mosi`と
`sdo`/`miso`がaliasです。同じ組から指定できるのは一方だけです。data方向は省略できますが、
少なくとも一方向が必要です。`controller_cs`と`device_cs`は両方指定するか、両方省略します。

### `I2C`

```python
i2c = I2C(scope, id, controller=controller, scl="SCL", sda="SDA")
i2c.add_peripheral(device=sensor, scl="SCL", sda="SDA")
```

複数のperipheralが宣言されたSCLとSDA netを共有します。

### `UART`

```python
UART(
    scope,
    id,
    left=controller,
    left_tx="TX",
    left_rx="RX",
    right=adapter,
    right_tx="TXD",
    right_rx="RXD",
)
```

left TXとright RX、left RXとright TXを接続します。どちらか一方向だけでも利用できます。

### Pin名warning

`SPI1_MOSI`、`SCLK`、`SDI`、`SDO`、`I2C_SDA`、`TXD`、`RXD`などの既知のpin名と
指定したroleが矛盾すると、CircuitDKがwarningを表示します。`GPIO2`のような汎用名も
そのまま利用できます。意図的な例外には理由付きoverrideを使います。

```python
sck=pin_override(
    sensor.pin("MISO"),
    reason="The shared legacy symbol has an incorrect pin name.",
)
```

## 値と単位

実用的な範囲のUnit定数を公開しています。

- 抵抗：`ohm`、`kohm`、`Mohm`
- 静電容量：`F`、`mF`、`uF`、`nF`、`pF`、`fF`
- インダクタンス：`H`、`mH`、`uH`、`nH`、`pH`
- 電圧：`kV`、`V`、`mV`、`uV`、`nV`
- 電流：`kA`、`A`、`mA`、`uA`、`nA`、`pA`、`fA`
- 周波数：`Hz`、`kHz`、`MHz`、`GHz`、`THz`

```python
resistance = 10 * kohm
capacitance = 100 * nF
inductance = 2.2 * mH
supply = 3.3 * V
clock = 16 * MHz
```

結果はimmutableかつDecimalベースの`Quantity`です。`Part`と`CircuitIR`では数値として
保持され、互換性のある次元同士で算術と比較を行えます。

```python
from decimal import Decimal

total = 1 * kohm + 500 * ohm
assert total == 1.5 * kohm
assert 1 * kohm <= total < 2 * kohm
assert (10 * kohm) / 2 == 5 * kohm
assert (10 * kohm) / (2 * kohm) == Decimal("5")
assert resistance.in_unit(ohm) == Decimal("10000")
```

加算、減算、大小比較では次元の一致が必要です。スカラーで割ると`Quantity`、同一次元の
`Quantity`で割ると無次元の`Decimal`を返します。スカラー乗算、単項`+`と`-`、`abs()`も
利用できます。

KiCadへ書き込む境界では、一般的な受動部品の短縮表記へ変換します。たとえば`470R`、
`4R7`、`3k3`、`100n`、`4u7`、`2m2`です。Pythonで直接選択した単位は維持されるため、
`0.3 * uF`は`0.3u`、`300 * nF`は`300n`になります。異なる倍率を混在させた計算では、
operandの順序に依存しないengineering prefixを自動選択します。

```python
total = 1 * kohm + 500 * ohm  # KiCad value: "1k5"
as_ohms = total.to(ohm)       # KiCad value: "1500R"
as_kohms = total.to(kohm)     # KiCad value: "1k5"
```

`to(unit)`は指定倍率で表現した等価な`Quantity`を返します。`in_unit(unit)`は数値部分の
`Decimal`だけを返します。明示した文字列値は変更しません。

自動表示では、すべての次元で共通のengineering prefix範囲である`T`、`G`、`M`、`k`、
base、`m`、`u`、`n`、`p`、`f`を使用します。公開定数は上記の実用範囲に限定しています。
周波数は`16MHz`のようにKiCad向け短縮表記でも`Hz`を維持し、電圧と電流は人間向けの単位を
維持します。

## `KicadProject`

```python
KicadProject(
    circuit,
    schematic,
    *,
    state_directory=".circuitdk",
    moved=None,
    validate_with_kicad=True,
)
```

高度な利用やtestでは、`symbol_resolver`、`footprint_resolver`、`kicad_cli`も注入できます。
通常のユーザーコードでは自動検出を使用してください。

| Member | 用途 |
| --- | --- |
| `circuit` | Desired stateを表す`Circuit`。 |
| `schematic` | 対象`.kicad_sch`の`Path`。 |
| `state_directory` | Last-applied stateとlibrary lock dataの保存directory。 |
| `moved` | 古い論理IDから新しい論理IDへのmapping。 |
| `state_path` | Managed state JSONのpath。 |
| `lock_path` | Library lock JSONのpath。 |
| `synth()` | Libraryを解決してdesired `CircuitIR`を返す。 |
| `plan()` | Desired stateと回路図を比較する。 |
| `drift()` | 前回deploy以降のmanagedなKiCad側変更を報告する。 |
| `deploy(backup=True)` | Managedな変更をatomicに適用する。 |
| `run_tests()` | Connectivity、pin、library、ERCを検査する。 |
| `inspect()` | Desired、actual、plan、drift、library dataをdictionaryで返す。 |
| `library_lock()` | Library hashを解決し、lockの問題を報告する。 |
| `adopt(reference, circuit_id)` | 既存KiCad symbolへ論理IDを付与する。 |
| `move(old_id, new_id)` | 回路図内のmanagedな論理IDを変更する。 |

通常のworkflowでは、安定した出力とexit code semanticsを提供するCLI commandを推奨します。
直接methodを呼ぶ方法はtestや独自の自動化に利用できます。

## Validation helper

`validate_pin_coverage(circuit_ir)`は、解決されたすべてのpinが接続済みまたは明示的な
no-connectかを検査します。結果objectは`.unspecified`とbooleanの`.ok` propertyを公開します。
通常は`circuitdk test`を使うことで、actual schematic connectivity、library、ERCの検査も
まとめて実行できます。

## Circuit IR

`CircuitIR`、`PartIR`、`NetIR`、`PinRef`は、synth後のimmutableなviewです。独自の解析やtestには
利用できますが、builderではありません。`Circuit`、`Part`、`Net`で回路を構築してから、
`project.synth()`を呼び出してください。

Alpha APIは今後変更される可能性があります。`circuitdk`からre-exportされる公開名が、
サポート対象のユーザーAPIです。`circuitdk.targets`以下は高度なbackend APIです。
