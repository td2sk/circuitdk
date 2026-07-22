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
| `add_intent(kind, subject, **parameters)` | 検証対象の独自semantic intentを追加する。 |
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
| `value` | 表示値。省略時はsymbol名。`str`または`Quantity`を指定可能。 |
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

## 再利用可能な部品と回路intent

### `Resistor`と`Capacitor`

```python
Resistor(scope, id, *, resistance, footprint=None)
Capacitor(scope, id, *, capacitance, footprint=None)
```

どちらも`pin1`と`pin2` propertyを公開し、対応する`Device:R`または`Device:C` symbolを設定
します。

### Pull resistor

```python
pull_down(scope, id, *, signal, ground, resistance, footprint=None)
pull_up(scope, id, *, signal, power, resistance, footprint=None)
```

作成した`Resistor`を返し、接続とdefault logic level intentの登録を行います。

### `DecouplingCapacitor`

```python
DecouplingCapacitor(
    scope,
    id,
    *,
    power_pin,
    ground,
    capacitance,
    footprint=None,
)
```

`.capacitor`を作成・公開し、power pinからgroundへ接続してdecoupling intentを登録します。

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

`.resistor`と`.led`を作成して直列に接続し、current-limiting intentを登録します。

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

### `Interface`と`SpiInterface`

`Interface(scope, id, *, pins={role: pin})`は、関連するpinをroleごとにまとめます。
`.pin(role)`でpinを取得し、`.connect(other, roles=None)`で共通roleまたは明示したrole mapを
接続します。

`SpiInterface`は`sck`、`mosi`、`miso`、`chip_select` roleを持つ型付きのconvenience
interfaceです。

## 値と単位

`ohm`、`kohm`、`F`、`uF`、`nF`、`V`を使用できます。

```python
resistance = 10 * kohm
capacitance = 100 * nF
supply = 3.3 * V
```

結果はimmutableな`Quantity`です。CircuitDKは`10 kΩ`、`100 nF`のような読みやすいKiCad値へ
正規化します。

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
| `run_tests()` | Conformance、intent、pin、library、ERCを検査する。 |
| `inspect()` | Desired、actual、plan、drift、library dataをdictionaryで返す。 |
| `library_lock()` | Library hashを解決し、lockの問題を報告する。 |
| `adopt(reference, circuit_id)` | 既存KiCad symbolへ論理IDを付与する。 |
| `move(old_id, new_id)` | 回路図内のmanagedな論理IDを変更する。 |

通常のworkflowでは、安定した出力とexit code semanticsを提供するCLI commandを推奨します。
直接methodを呼ぶ方法はtestや独自の自動化に利用できます。

## Validation helper

`validate_pin_coverage(circuit_ir)`は、解決されたすべてのpinが接続済みまたは明示的な
no-connectかを検査します。`validate_intents(circuit_ir)`は、再利用constructが作成した
semantic intentを検査します。結果objectは`.issues`とbooleanの`.ok` propertyを公開します。
通常は`circuitdk test`を使うことで、actual schematicとERCの検査もまとめて実行できます。

## Circuit IR

`CircuitIR`、`PartIR`、`NetIR`、`PinRef`、`IntentIR`は、synth後のimmutableなviewです。独自の
解析やtestには利用できますが、builderではありません。`Circuit`、`Part`、`Net`、再利用
constructで回路を構築してから、`project.synth()`を呼び出してください。

Alpha APIは今後変更される可能性があります。`circuitdk`からre-exportされる公開名が、
サポート対象のユーザーAPIです。`circuitdk.targets`以下は高度なbackend APIです。
