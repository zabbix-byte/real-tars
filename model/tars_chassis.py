"""
TARS — Chasis paramétrico generado con Build123d.

Genera las 3 piezas del chasis TARS (234 mm de alto) listas para imprimir
en PETG en Bambu Lab X2D / X1 / P1S (caben enteras, sin partir):

  1. bloque_central    (78 × 39 × 234 mm)  — caja monolítica con techo cerrado
                                              y trasera COMPLETAMENTE abierta.
                                              Aloja: OLED, cámara, VL53L1X, XIAO,
                                              MT3608, batería, servos A+B.
  2. brazo_izquierdo   (39 × 39 × 234 mm)  — unido por horn servo + pivote M3.
  3. brazo_derecho     (39 × 39 × 234 mm)  — simétrico del izquierdo.

Sistema de unión brazo ↔ central:
  - Eje motriz:  servo EMAX ES08MD fijado DENTRO del central (4× M2 a postes internos).
                 El horn del servo atraviesa la pared interior del central y entra en
                 el brazo, donde se atornilla al brazo con 4× M2.
  - Eje libre:   tornillo M3 superior con bushing de nylon + arandela. Mantiene el
                 brazo alineado y absorbe el peso sin estresar el servo.
  - Gap:         1,5 mm entre central y brazo para oscilar sin rozar.

Fuente de verdad de cotas: PHASE3_MECHANICS.md
Todos los valores en mm.

Uso:
    pip install build123d
    python tars_chassis.py

Salidas (en ./out/):
    bloque_central.stl / .3mf
    brazo_izquierdo.stl / .3mf
    brazo_derecho.stl  / .3mf
    PREVIEW_tars_robot.stl / .3mf   (vista completa ensamblada, sólo referencia)

Abre los .3mf directamente en Bambu Studio, asigna perfil PETG y lamina.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import zipfile

from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    BuildSketch,
    Circle,
    Color,
    Compound,
    Cylinder,
    Location,
    Locations,
    Mode,
    Part,
    Plane,
    Pos,
    Rectangle,
    Rot,
    Text,
    export_stl,
    extrude,
    fillet,
)
from build123d import Mesher

# =============================================================================
# PARÁMETROS CANÓNICOS (editar aquí para redimensionar todo el robot)
# =============================================================================

# --- Geometría global -------------------------------------------------------
UNIT = 39.0              # Unidad modular (mm).
HEIGHT = 6 * UNIT        # 234 mm  (TARS película proporción ~6:2 ancho)
DEPTH = 1 * UNIT         # 39 mm
WIDTH_CENTRAL = 2 * UNIT # 78 mm
WIDTH_ARM = 1 * UNIT     # 39 mm
WIDTH_TOTAL = WIDTH_CENTRAL + 2 * WIDTH_ARM  # 156 mm

WALL = 3.0               # Grosor de pared exterior
WALL_INNER = 2.0         # Grosor de tabiques internos
FILLET_EDGE = 0.0        # Bordes exteriores AFILADOS (estilo monolito TARS)
FILLET_INNER = 1.0       # Radio de redondeo en aperturas

# --- Separación entre brazos y central --------------------------------------
ARM_GAP = 1.5            # Holgura para oscilación del brazo sin rozar

# --- Sistema de unión brazo ↔ central ---------------------------------------
# Eje motriz (horn del servo):
SERVO_HORN_HOLE_D = 8.0          # (compat.) ya no se usa horn — press-fit directo
# --- PRESS-FIT del brazo sobre el eje estriado del servo -------------------
# El ES08MDII tiene eje estriado de latón de ≈4.8 mm (20 dientes). En vez
# de usar el horn de plástico, el brazo se monta DIRECTAMENTE sobre el eje:
# se imprime un agujero ciego ligeramente más pequeño que el eje; al
# presionar, los dientes de latón muerden el PLA y crean un acople positivo
# que NO se afloja con el par del servo. El tornillo central M2.5 (incluido
# con el servo) se mete desde el EXTERIOR del brazo y retiene todo
# axialmente contra el eje.
SPLINE_D = 4.6                   # ø del agujero press-fit (eje real 4.8 →
                                 # agujero 0.2 mm menor para que muerda)
SPLINE_DEPTH = 5.5               # profundidad del agujero ciego (eje sobresale ~4 mm)
SPLINE_BOSS_D = 9.0              # ø del refuerzo cilíndrico alrededor del press-fit
SPLINE_BOSS_H = 6.0              # altura del refuerzo (hacia el interior del brazo)
SCREW_M25_CLEARANCE_D = 3.0      # paso del M2.5 central del servo
SCREW_M25_HEAD_D = 5.2           # ø del avellanado para la cabeza del tornillo
SERVO_BODY_W = 23.5              # EMAX ES08MDII: cuerpo 23.5 × 11.6 × 24.5 mm
SERVO_BODY_H = 11.6              # grosor
SERVO_BODY_D = 24.5              # alto cuerpo (sin torreta del horn)
SERVO_TOWER_H = 5.0              # altura extra de la torreta de engranajes (ø~10)
SERVO_TOWER_D = 10.5             # diámetro torreta redonda del lado del horn
SERVO_SLACK = 0.5                # holgura TOTAL para la cuna (0.25 por lado)
SERVO_MOUNT_SCREW_D = 2.2        # M2 que fijan el servo al central
SERVO_MOUNT_SPACING = 32.5       # Datasheet ES08MDII: distancia entre agujeros

# Eje libre superior (pivote M3 + bushing):
PIVOT_Z = 210.0                  # Altura del pivote superior (HEIGHT - 24)
PIVOT_SCREW_D = 3.2              # M3 pasante
PIVOT_BOSS_D = 8.0               # Diámetro del refuerzo cilíndrico alrededor

# --- Tapa trasera (acceso completo al interior, SIN TORNILLOS) --------------
REAR_LID_T = 3.0                 # Grosor de la tapa trasera
# Sistema snap-fit: 2 ganchos rígidos arriba + 2 clips cantilever flexibles abajo.
# La tapa se inserta con los ganchos superiores bajo el labio interior y luego
# se presiona el borde inferior para que los clips claven en sus ranuras.
REAR_LID_HOOK_X = [-25.0, 25.0]          # Posiciones X de los 2 ganchos superiores
REAR_LID_CLIP_X = [-25.0, 25.0]          # Posiciones X de los 2 clips inferiores
REAR_LID_RAIL_Z = [70.0, 160.0]          # Alturas de los 2 rails laterales anti-combeo
REAR_LID_HOOK_Z = HEIGHT - 4 - 10.0      # Z del gancho (bajo el labio superior)
REAR_LID_CLIP_Z = 15.0                   # Z del clip inferior
REAR_LID_SNAP_W = 14.0                   # Ancho de cada snap
REAR_LID_BARB = 1.2                      # Saliente de la barba del snap

# --- Tapa superior (SIN TORNILLOS, snap-fit por 4 lenguetas) -----------------
TOP_LID_T = 4.0                  # Grosor de la tapa superior
TOP_LID_TONGUE = 1.5             # Alto del tongue (se hunde en el interior)
TOP_LID_TAB_W = 8.0              # Ancho de cada tab snap
TOP_LID_TAB_H = 5.0              # Largo que se adentra la tab
TOP_LID_BARB = 0.7                # Saliente de la barba

# --- Ventanas en la cara frontal del bloque central --------------------------
# Z = altura desde la base (0 = suelo, HEIGHT = tapa). Con HEIGHT=234:
OLED_Z0, OLED_Z1 = 162.0, 206.0         # Ventana visible 72 × 44 mm (pantalla sin marco)
OLED_W, OLED_H = 72.0, 44.0
OLED_PCB_W, OLED_PCB_H = 71.0, 46.0     # PCB total — cabe dentro del interior (72×44 comp)
OLED_PCB_DEPTH = 10.0                   # profundidad desde la pared frontal interior

SERVO_Z0, SERVO_Z1 = 110.0, 180.0       # Zona donde viven los servos
SERVO_AXIS_Z = 145.0                    # Eje de rotación del brazo

TOF_Z = 215.0                           # ToF VL53L1X (algo por debajo de la cámara)
TOF_OFFSET_X = 14.0
TOF_HOLE_D = 4.0

CAM_Z = 228.0                           # Centro lente OV2640 (alineado con Sense)
CAM_HOLE_D = 7.2                        # Barril de la lente OV2640 (~ø7) + 0.2 mm holgura
# Módulo cámara OV2640 (XIAO Sense): PCB 8.5×8.5 mm, barril lente ø~7 × ~5 mm
CAM_PCB_W = 8.5
CAM_PCB_H = 8.5
CAM_PCB_SLACK = 0.6                     # holgura total en el bolsillo PCB
CAM_POCKET_DEPTH = 3.0                  # profundidad del bolsillo hacia +Y
CAM_RETAIN_LIP = 1.0                    # labio superior/inferior que pellizca la PCB

SPK_Z = 25.0                            # Centro altavoz rectangular (parte baja)
SPK_W = 70.0                            # Altavoz rectangular 70 × 30 × 15 mm
SPK_H = 30.0                            # alto del marco (eje Z)
SPK_T = 15.0                            # profundidad total del altavoz
SPK_SLACK = 0.6                         # holgura total (0.3 por lado)
SPK_SCREW_D = 2.2                       # 4 tornillos M2 en las esquinas
SPK_SCREW_DX = 62.0                     # separación horizontal entre tornillos
SPK_SCREW_DZ = 22.0                     # separación vertical entre tornillos

SWITCH_Z = 30.0                         # Interruptor rocker en la tapa trasera
SWITCH_HOLE_D = 6.5                     # Rocker redondo ø6.5 mm

BAT_Z0, BAT_Z1 = 30.0, 120.0            # HXJN 60×90×6 mm, pegada a la pared trasera (90 mm)
BAT_W, BAT_H = 60.0, 90.0

# --- Pies / ventilación ------------------------------------------------------
FOOT_H = 4.0
VENT_HOLE_D = 4.0

# --- Montajes M2 -------------------------------------------------------------
M2_HOLE_D = 2.2          # Agujero pasante M2
M2_POST_D = 5.0          # Diámetro del poste roscado
M2_POST_H = 6.0

# --- Partido para impresión (Bambu Lab X2D: volumen 256×256×260 mm) ----------
# Las piezas de 351 mm NO caben en Z. Se parten horizontalmente a SPLIT_Z y
# se unen en montaje con 2 pines dowel de alineación + 2 tornillos M3 internos
# que atraviesan el plano del corte. Los insertos M3 (heat-set) van en la
# mitad inferior; los tornillos entran desde la mitad superior.
PRINT_MAX_Z = 256.0              # Altura máxima aprovechable de la X2D (margen 4mm)
SPLIT_ENABLED = True             # Poner False si tienes una impresora con Z≥355
SPLIT_Z = 175.0                  # Altura del corte (aprox. mitad del chasis)
SPLIT_DOWEL_D = 4.0              # Diámetro pin de alineación
SPLIT_DOWEL_HOLE_D = 4.2         # Agujero ciego del pin (holgura)
SPLIT_DOWEL_H = 8.0              # Profundidad del pin dentro de cada mitad
SPLIT_SCREW_D = 3.2              # M3 pasante (en la mitad superior)
SPLIT_INSERT_D = 4.2             # Inserto heat-set (en la mitad inferior)
SPLIT_INSERT_DEPTH = 6.0

# --- Salida ------------------------------------------------------------------
OUT_DIR = Path(__file__).parent / "out"

# --- Paleta de colores (PETG filamentos típicos Bambu Lab) -------------------
COLORS = {
    "bloque_central":    (0.15, 0.15, 0.17, 1.0),   # negro grafito
    "tapa_trasera":      (0.25, 0.25, 0.28, 1.0),   # gris oscuro
    "tapa_superior":     (0.25, 0.25, 0.28, 1.0),   # gris oscuro
    "brazo_izquierdo":   (0.85, 0.15, 0.15, 1.0),   # rojo TARS
    "brazo_derecho":     (0.85, 0.15, 0.15, 1.0),   # rojo TARS
    "soporte_servos":    (0.95, 0.85, 0.15, 1.0),   # amarillo (pieza de refuerzo)
}

# Slot AMS asignado a cada pieza (1..4). Al abrir el 3MF en Bambu Studio,
# cada objeto se pre-asigna al filamento de ese slot.
#   Slot 1 → Negro  (bloque central)
#   Slot 2 → Gris   (tapas)
#   Slot 3 → Rojo   (brazos)
#   Slot 4 → Amarillo (soporte servos)
FILAMENT_SLOT = {
    "bloque_central":  1,
    "tapa_trasera":    2,
    "tapa_superior":   2,
    "brazo_izquierdo": 3,
    "brazo_derecho":   3,
    "soporte_servos":  4,
}

# =============================================================================
# HELPERS
# =============================================================================


def hollow_box(
    width: float,
    depth: float,
    height: float,
    wall: float = WALL,
    open_top: bool = True,
    open_back: bool = False,
) -> Part:
    """Caja hueca con pared `wall`.

    open_top  : sin tapa superior (se cierra con `tapa_superior`).
    open_back : sin pared trasera (se cierra con `tapa_trasera`). La pared trasera
                es la cara con Y positivo (+Y). Se deja un rebaje perimetral de
                `wall` mm para que la tapa trasera encaje al ras.
    """
    with BuildPart() as hb:
        Box(width, depth, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        # Bordes exteriores afilados (estilo monolito TARS). Si se quiere
        # aristas suaves, elevar FILLET_EDGE > 0.
        if FILLET_EDGE > 0:
            edges = hb.edges().filter_by(Axis.Z)
            if len(edges) > 0:
                try:
                    fillet(edges, radius=FILLET_EDGE)
                except Exception:
                    pass
    part = hb.part

    # Vaciado interior: se hace FUERA del BuildPart con resta booleana
    # explícita, porque Box(..., mode=SUBTRACT).locate() dentro del
    # contexto ignora la traslación y resta en el origen.
    inner_w = width - 2 * wall
    inner_d = depth - 2 * wall
    inner_h = height - wall - (0 if open_top else wall)
    inner = Box(
        inner_w, inner_d, inner_h,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((0, 0, wall)))
    part = part - inner

    # Apertura trasera (+Y) con labio perimetral para insertos M3.
    if open_back:
        REAR_MARGIN = 7.0
        cut_w = width - 2 * wall - 2 * REAR_MARGIN
        cut_h = height - wall - 2 * REAR_MARGIN
        cut_d = wall * 2 + 0.4  # cruza la pared trasera con holgura
        back_cutter = Box(
            cut_w, cut_d, cut_h,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((0, depth / 2 - wall, wall + REAR_MARGIN)))
        part = part - back_cutter

    return part


def front_rect_window(
    part: Part,
    z_center: float,
    w: float,
    h: float,
    depth: float,
    fillet_r: float = FILLET_INNER,
) -> Part:
    """Resta un rectángulo en la cara frontal (Y = -depth/2)."""
    cutter_d = WALL * 3  # suficiente para atravesar la pared
    with BuildPart() as c:
        Box(w, cutter_d, h, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        if fillet_r > 0:
            fillet(c.edges().filter_by(Axis.Y), radius=fillet_r)
    cutter = c.part.locate(Location((0, -depth / 2, z_center)))
    return part - cutter


def front_circle_hole(
    part: Part,
    x: float,
    z: float,
    diameter: float,
    depth: float,
) -> Part:
    """Agujero circular en la cara frontal (eje Y)."""
    cutter = Cylinder(
        diameter / 2,
        WALL * 3,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
        rotation=(90, 0, 0),
    ).locate(Location((x, -depth / 2, z)))
    return part - cutter


def side_circle_hole(
    part: Part,
    side: str,  # "left" or "right"
    z: float,
    diameter: float,
    width: float,
) -> Part:
    """Agujero circular en la cara lateral (eje X)."""
    x = -width / 2 if side == "left" else width / 2
    cutter = Cylinder(
        diameter / 2,
        WALL * 3,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
        rotation=(0, 90, 0),
    ).locate(Location((x, 0, z)))
    return part - cutter


# ---------------------------------------------------------------------------
# DETALLES ESTÉTICOS: líneas de panel + texto grabado (estilo TARS de la peli)
# ---------------------------------------------------------------------------
def engrave_panel_line(
    part: Part,
    z: float,
    w: float,
    d: float,
    depth: float = 0.6,
    thickness: float = 1.2,
) -> Part:
    """Graba una línea horizontal fina en las 4 caras exteriores a altura z.

    No atraviesa la pieza; sólo resta `depth` mm en cada cara.
    """
    # Cara frontal (y = -d/2) y trasera (y = +d/2)
    fb = Box(w + 2.0, depth * 2, thickness,
             align=(Align.CENTER, Align.CENTER, Align.CENTER))
    part = part - fb.locate(Location((0, -d / 2, z)))
    part = part - fb.locate(Location((0, +d / 2, z)))
    # Caras laterales (x = ±w/2)
    lr = Box(depth * 2, d + 2.0, thickness,
             align=(Align.CENTER, Align.CENTER, Align.CENTER))
    part = part - lr.locate(Location((-w / 2, 0, z)))
    part = part - lr.locate(Location((+w / 2, 0, z)))
    return part


def engrave_panel_lines_modular(part: Part, w: float, d: float, units: int = 9) -> Part:
    """Graba una línea a cada múltiplo de UNIT (39 mm) excepto en z=0 y z=top."""
    for i in range(1, units):
        part = engrave_panel_line(part, i * UNIT, w, d)
    return part


def engrave_vertical_slats(
    part: Part,
    w: float,
    d: float,
    height: float,
    pitch: float = 8.0,
    line_thickness: float = 0.8,
    depth: float = 0.6,
    z_margin: float = 4.0,
    faces: tuple[str, ...] = ("front", "back", "left", "right"),
) -> Part:
    """Ranuras VERTICALES paralelas — el patrón principal del TARS de la peli.

    Simula el apilamiento de listones verticales que recubre todo el cuerpo.
    Cada cara exterior queda dividida en bandas verticales por líneas finas
    grabadas desde z_margin hasta height-z_margin.
    """
    z_len = height - 2 * z_margin
    z_c = z_margin + z_len / 2
    # Cutter para las caras frontal/trasera (ranura vertical en eje Z)
    fb = Box(line_thickness, depth * 2, z_len,
             align=(Align.CENTER, Align.CENTER, Align.CENTER))
    # Cutter para las caras laterales
    lr = Box(depth * 2, line_thickness, z_len,
             align=(Align.CENTER, Align.CENTER, Align.CENTER))
    # --- Frontal/Trasera: ranuras a lo ancho (eje X) ---
    if "front" in faces or "back" in faces:
        n = int(w // pitch)
        if n > 1:
            step = w / n
            for i in range(1, n):
                x = -w / 2 + i * step
                if "front" in faces:
                    part = part - fb.locate(Location((x, -d / 2, z_c)))
                if "back" in faces:
                    part = part - fb.locate(Location((x, +d / 2, z_c)))
    # --- Laterales: ranuras a lo largo del fondo (eje Y) ---
    if "left" in faces or "right" in faces:
        n = int(d // pitch)
        if n > 1:
            step = d / n
            for i in range(1, n):
                y = -d / 2 + i * step
                if "left" in faces:
                    part = part - lr.locate(Location((-w / 2, y, z_c)))
                if "right" in faces:
                    part = part - lr.locate(Location((+w / 2, y, z_c)))
    return part


def engrave_hatch_panel(
    part: Part,
    x_center: float,
    z0: float,
    z1: float,
    panel_w: float,
    d: float,
    pitch: float = 1.2,
    line_thickness: float = 0.6,
    depth: float = 0.5,
) -> Part:
    """Panel rectangular de rayado horizontal denso en la cara frontal.

    Usado para simular las "rejillas" que flanquean las pantallas en TARS.
    """
    cutter = Box(panel_w, depth * 2, line_thickness,
                 align=(Align.CENTER, Align.CENTER, Align.CENTER))
    z = z0
    while z <= z1:
        part = part - cutter.locate(Location((x_center, -d / 2, z)))
        z += pitch
    return part


def engrave_front_text(
    part: Part,
    text: str,
    z: float,
    d: float,
    size: float = 10.0,
    depth: float = 0.6,
) -> Part:
    """Graba texto en la cara FRONTAL (y = -d/2) centrado en (x=0, z)."""
    with BuildSketch(Plane.XZ) as sk:
        with Locations((0, z)):
            Text(text, font_size=size, align=(Align.CENTER, Align.CENTER))
    # Extrude along +Y (plane normal). Rotate 180° around Z to mirror letters
    # para que se lean correctamente desde -Y (frente).
    carve = extrude(sk.sketch, amount=depth + 0.2)
    carve = carve.rotate(Axis.Z, 180)
    # Mover hacia la cara frontal: el sólido queda de y=[-d/2-0.1, -d/2+depth+0.1]
    carve = carve.moved(Location((0, -d / 2 + depth + 0.1, 0)))
    return part - carve


def _as_part_global(s):
    """Boolean ops can return a ShapeList/Compound. Return the largest solid as Part."""
    if isinstance(s, Part):
        return s
    try:
        items = list(s)
    except TypeError:
        items = [s]
    solids = []
    for it in items:
        try:
            solids.extend(it.solids())
        except Exception:
            pass
    if not solids:
        solids = items
    solids.sort(key=lambda x: x.volume if hasattr(x, "volume") else 0, reverse=True)
    return Part(solids[0].wrapped) if not isinstance(solids[0], Part) else solids[0]


def split_piece(
    part: Part,
    z_cut: float,
    width: float,
    depth: float,
    dowel_positions: list[tuple[float, float]] | None = None,
    screw_positions: list[tuple[float, float]] | None = None,
) -> tuple[Part, Part]:
    """Divide una pieza en dos mitades en z=z_cut y añade sistema de anclaje.

    dowel_positions : lista de (x, y) donde irán los pines de alineación ø4.
                       El pin (cilindro macizo) se añade a la mitad INFERIOR
                       sobresaliendo hacia arriba y se resta un agujero ciego
                       en la mitad SUPERIOR.
    screw_positions : lista de (x, y) donde irán los tornillos M3.
                       Agujero pasante en la mitad SUPERIOR + hueco para inserto
                       heat-set en la mitad INFERIOR (abierto hacia arriba).

    Devuelve (bottom, top). La mitad superior se devuelve trasladada a z=0 para
    que se pueda imprimir directamente sobre la cama.
    """
    if dowel_positions is None:
        dowel_positions = [
            (-width / 2 + WALL, -depth / 2 + WALL),
            (+width / 2 - WALL, -depth / 2 + WALL),
            (-width / 2 + WALL, +depth / 2 - WALL),
            (+width / 2 - WALL, +depth / 2 - WALL),
        ]
    if screw_positions is None:
        screw_positions = [
            (-width / 2 + WALL, 0),
            (+width / 2 - WALL, 0),
        ]

    # Cutters rectangulares para dividir la pieza
    big = max(width, depth) * 4
    cutter_bottom = Box(big, big, 1000, align=(Align.CENTER, Align.CENTER, Align.MIN)).locate(
        Location((0, 0, z_cut))
    )
    cutter_top = Box(big, big, 1000, align=(Align.CENTER, Align.CENTER, Align.MAX)).locate(
        Location((0, 0, z_cut))
    )

    def _as_part(s):
        return _as_part_global(s)

    bottom = _as_part(part - cutter_bottom)
    top = _as_part(part - cutter_top)

    # Pines de alineación: cilindro macizo añadido al bottom (sobresale SPLIT_DOWEL_H
    # por encima del plano de corte) + agujero ciego en el top.
    for (px, py) in dowel_positions:
        dowel = Cylinder(
            SPLIT_DOWEL_D / 2,
            SPLIT_DOWEL_H,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((px, py, z_cut)))
        bottom = bottom + dowel

        dowel_hole = Cylinder(
            SPLIT_DOWEL_HOLE_D / 2,
            SPLIT_DOWEL_H + 0.5,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((px, py, z_cut)))
        top = top - dowel_hole

    # Tornillos M3: agujero pasante en top + hueco para inserto heat-set en bottom.
    for (sx, sy) in screw_positions:
        # Inserto heat-set (abierto hacia arriba en el bottom)
        insert = Cylinder(
            SPLIT_INSERT_D / 2,
            SPLIT_INSERT_DEPTH,
            align=(Align.CENTER, Align.CENTER, Align.MAX),
        ).locate(Location((sx, sy, z_cut)))
        bottom = bottom - insert

        # Pasante en el top (toda la altura de la mitad superior sería excesivo
        # — un canal de 15 mm basta para meter un M3×12).
        screw_hole = Cylinder(
            SPLIT_SCREW_D / 2,
            15.0,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((sx, sy, z_cut)))
        top = top - screw_hole

    # Trasladar la mitad superior a z=0 para imprimir
    top = top.locate(Location((0, 0, -z_cut)))

    return bottom, top


# =============================================================================
# BLOQUE CENTRAL (78 × 39 × 351)
# =============================================================================


def make_bloque_central() -> Part:
    # El bloque central mide HEIGHT - TAPA_T para que la tapa superior
    # quede al ras con los brazos. Trasera abierta con labio perimetral
    # para atornillar la tapa trasera desmontable.
    TAPA_T = 4.0
    H_CENTRAL = HEIGHT - TAPA_T
    p = hollow_box(
        WIDTH_CENTRAL, DEPTH, H_CENTRAL,
        wall=WALL, open_top=True, open_back=True,
    )

    # Agrando la apertura trasera a un marco uniforme de WALL mm alrededor,
    # para que la tapa trasera encaje al ras (flush) con los brazos.
    # Ventana: (WIDTH - 2*WALL) × (H_CENTRAL - 2*WALL)
    rear_window_cutter = Box(
        WIDTH_CENTRAL - 2 * WALL,
        WALL * 2 + 0.4,
        H_CENTRAL - 2 * WALL,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((0, DEPTH / 2 - WALL, WALL)))
    p = p - rear_window_cutter

    # --- Ventana OLED (pantalla principal, sin marco — el cristal tapa la ranura)
    p = front_rect_window(p, (OLED_Z0 + OLED_Z1) / 2, OLED_W, OLED_H, DEPTH)

    # Pocket interior para el PCB de la OLED (76 × 48 × 10 mm) pegado a la
    # pared frontal, con pequeño reborde (2 mm a cada lado) que sirve de
    # tope para el cristal — la pantalla empuja desde dentro hacia fuera y
    # queda a ras de la cara frontal.
    oled_pocket = Box(
        OLED_PCB_W,
        OLED_PCB_DEPTH,
        OLED_PCB_H,
        align=(Align.CENTER, Align.MIN, Align.CENTER),
    ).locate(Location((0, -DEPTH / 2 + WALL, (OLED_Z0 + OLED_Z1) / 2)))
    p = p - oled_pocket

    # --- Altavoz rectangular 70 × 30 × 15 mm (SIN tornillos, press-fit)
    # El altavoz entra desde atrás en un pocket 70.6 × 30.6 × 15.3 mm.
    # Cuatro pequeños labios internos (0.6 mm hacia dentro) clavan contra
    # el marco trasero del altavoz al insertarlo, evitando que se salga.
    spk_pocket = Box(
        SPK_W + SPK_SLACK,
        SPK_T + 0.3,
        SPK_H + SPK_SLACK,
        align=(Align.CENTER, Align.MIN, Align.CENTER),
    ).locate(Location((0, -DEPTH / 2 + WALL, SPK_Z)))
    p = p - spk_pocket

    # 4 labios de retención (uno por esquina, en la cara interior trasera
    # del pocket). Al insertar el altavoz, pasan por encima del marco y
    # cierran por detrás (snap).
    for sx in (-1, 1):
        for sz in (-1, 1):
            lip = Box(
                6.0, 1.5, 2.0,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
            ).locate(Location((
                sx * (SPK_W / 2 - 3.0),
                -DEPTH / 2 + WALL + SPK_T - 0.5,
                SPK_Z + sz * (SPK_H / 2 - 1.0),
            )))
            p = p + lip

    # (Sin rejilla visible en la pared frontal: el diseño TARS se mantiene
    # limpio. El sonido sale lateralmente por las juntas con la tapa trasera
    # y por el hueco posterior del pocket.)

    # --- Lente cámara (OV2640 en XIAO Sense): barril ø7.5 atraviesa la pared
    #     frontal y sobresale 1 mm; PCB 8.5×8.5 queda en un pocket interior
    #     pellizcado por dos labios (press-fit).
    p = front_circle_hole(p, 0, CAM_Z, CAM_HOLE_D, DEPTH)

    # Bolsillo cuadrado para la PCB de la cámara, inmediatamente detrás de
    # la pared frontal (desde y=-DEPTH/2+WALL hacia +Y, CAM_POCKET_DEPTH mm).
    cam_pocket_w = CAM_PCB_W + CAM_PCB_SLACK
    cam_pocket_h = CAM_PCB_H + CAM_PCB_SLACK
    cam_pocket = Box(
        cam_pocket_w,
        CAM_POCKET_DEPTH,
        cam_pocket_h,
        align=(Align.CENTER, Align.MIN, Align.CENTER),
    ).locate(Location((0, -DEPTH / 2 + WALL, CAM_Z)))
    p = p - cam_pocket

    # Dos labios (arriba y abajo) que cierran parcialmente el pocket para
    # impedir que la PCB se salga hacia atrás. Dejan una ranura central de
    # (cam_pocket_h - 2*lip) mm por donde entra la PCB deslizando lateralmente
    # o se introduce con un pequeño chasquido (el labio flexa 0.2-0.3 mm).
    lip_thick = 1.2   # grosor del labio en Y (se queda dentro del pocket)
    for sign in (-1, 1):
        lip = Box(
            cam_pocket_w + 2,     # un poco más ancho que el pocket
            lip_thick,
            CAM_RETAIN_LIP,
            align=(Align.CENTER, Align.MIN, Align.MIN if sign > 0 else Align.MAX),
        ).locate(Location((
            0,
            -DEPTH / 2 + WALL + CAM_POCKET_DEPTH - lip_thick,
            CAM_Z + sign * (cam_pocket_h / 2),
        )))
        p = p + lip

    # --- Micrófono del XIAO (ø2 mm), a la izquierda de la cámara ---
    # Va en la misma placa que la cámara, por eso lo perforamos al lado.
    p = front_circle_hole(p, -8.0, CAM_Z, 2.0, DEPTH)

    # --- VL53L1X (ToF, hasta 4 m), ventana ø4 mm — a su propia altura ---
    p = front_circle_hole(p, TOF_OFFSET_X, TOF_Z, TOF_HOLE_D, DEPTH)

    # Pocket interior 18×14×3 mm para PCB típica del VL53L1X (press-fit,
    # sin tornillos). Dos labios laterales de 0.6 mm pellizcan el PCB.
    tof_pocket = Box(
        18.0, 3.0, 14.0,
        align=(Align.CENTER, Align.MIN, Align.CENTER),
    ).locate(Location((TOF_OFFSET_X, -DEPTH / 2 + WALL, TOF_Z)))
    p = p - tof_pocket
    for sx in (-1, 1):
        tof_lip = Box(
            1.0, 1.2, 8.0,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location((
            TOF_OFFSET_X + sx * 8.0,
            -DEPTH / 2 + WALL + 2.8,
            TOF_Z,
        )))
        p = p + tof_lip

    import math  # (usado más abajo para el círculo de tornillos)

    # -------------------------------------------------------------------
    # SISTEMA DE UNIÓN BRAZO ↔ CENTRAL
    # -------------------------------------------------------------------
    # Para cada lado (izquierdo y derecho) se añade:
    #   (a) Agujero pasante para el horn del servo (z = SERVO_AXIS_Z)
    #   (b) Circulo de 4 tornillos M2 para fijar el horn al brazo (reservado
    #       en el brazo; el central sólo tiene el pasante del eje)
    #   (c) Cuna interior para el cuerpo del servo, con 2 orejas de M2
    # -------------------------------------------------------------------
    for side in ("left", "right"):
        x_side = -WIDTH_CENTRAL / 2 if side == "left" else WIDTH_CENTRAL / 2

        # (a) Paso del horn
        p = side_circle_hole(
            p, side=side, z=SERVO_AXIS_Z,
            diameter=SERVO_HORN_HOLE_D, width=WIDTH_CENTRAL,
        )

        # (c) Cuna del servo — hueco preciso para el ES08MDII (23.5×11.6×24.5)
        # El servo entra desde el brazo (lateral) con el eje del horn apuntando
        # hacia el central. La cuna se talla en la pared lateral del central
        # con 0.25 mm de holgura por lado.
        cuna = Box(
            SERVO_BODY_H + SERVO_SLACK,    # en X: grosor del servo (11.6)
            SERVO_BODY_W + SERVO_SLACK,    # en Y: ancho (23.5)
            SERVO_BODY_D + SERVO_SLACK,    # en Z: alto (24.5)
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location((
            x_side + (SERVO_BODY_H / 2 + WALL / 2) * (1 if side == "left" else -1),
            0,
            SERVO_AXIS_Z - 2.0,            # eje del horn está desplazado del centro del cuerpo
        )))
        p = p - cuna

        # Alojamiento de la torreta circular del horn (ø10.5 × 5 mm)
        tower = Cylinder(
            SERVO_TOWER_D / 2 + 0.3,
            SERVO_TOWER_H + 0.3,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            rotation=(0, 90, 0),
        ).locate(Location((x_side, 0, SERVO_AXIS_Z)))
        p = p - tower

        # Salida del cable del servo (hacia la pared trasera)
        cable_out = Box(
            SERVO_BODY_H + SERVO_SLACK,
            4.0,
            4.0,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location((
            x_side + (SERVO_BODY_H / 2 + WALL / 2) * (1 if side == "left" else -1),
            SERVO_BODY_W / 2 - 2.0,
            SERVO_AXIS_Z - SERVO_BODY_D / 2 + 2.0,
        )))
        p = p - cable_out

        # (Sin tornillos de montaje: la cuna del servo + la torreta + el
        # horn atornillado al brazo retienen el servo cinemáticamente.)

    # -------------------------------------------------------------------
    # SNAP-FIT DE LA TAPA TRASERA (flush, sin tornillos)
    # -------------------------------------------------------------------
    # La tapa encaja DENTRO del marco trasero (no por detrás). Sus clips
    # cantilever salen por la cara interior y enganchan en muescas
    # talladas en las caras INTERIORES del marco superior e inferior.
    #
    #   Marco superior (z = H_CENTRAL-WALL .. H_CENTRAL): muesca en la cara
    #     -Z (mirando hacia la cavidad).
    #   Marco inferior (z = 0 .. WALL): muesca en la cara +Z.
    #
    # Y se añade una muesca lateral en cada montante vertical del marco
    # para los 2 rails de la tapa (anti-combeo).
    #
    # La muesca es un rebaje rectangular de ~1 mm de profundidad, suficiente
    # para que la barba del clip caiga dentro y se oiga "click".
    LID_BARB_D = 1.0          # profundidad de la muesca (= altura del barb)
    LID_NOTCH_THK = WALL - 0.8  # deja 0.8 mm de pared en la muesca (no pasante)

    # Muesca en el marco SUPERIOR (cara interior, mirando hacia -Z)
    for cx in REAR_LID_CLIP_X:
        notch = Box(
            REAR_LID_SNAP_W + 0.4,
            LID_NOTCH_THK,
            LID_BARB_D + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((
            cx,
            DEPTH / 2 - WALL / 2,
            H_CENTRAL - WALL - (LID_BARB_D + 0.2),
        )))
        p = p - notch

    # Muesca en el marco INFERIOR (cara interior, mirando hacia +Z)
    for cx in REAR_LID_CLIP_X:
        notch = Box(
            REAR_LID_SNAP_W + 0.4,
            LID_NOTCH_THK,
            LID_BARB_D + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((
            cx,
            DEPTH / 2 - WALL / 2,
            WALL,
        )))
        p = p - notch

    # Muescas laterales (izq/dcha) a 2 alturas para los rails anti-combeo
    for rz in REAR_LID_RAIL_Z:
        for sx in (-1, 1):
            rail_notch = Box(
                LID_BARB_D + 0.2,
                LID_NOTCH_THK,
                10.0,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
            ).locate(Location((
                sx * (WIDTH_CENTRAL / 2 - WALL + (LID_BARB_D + 0.2) / 2),
                DEPTH / 2 - WALL / 2,
                rz,
            )))
            p = p - rail_notch

    # -------------------------------------------------------------------
    # CUNA DE LA BATERÍA (HXJN LiPo 606090 — 60 × 90 × 6 mm)
    # -------------------------------------------------------------------
    # La batería va DE PIE apoyada contra la pared frontal (-Y), con su
    # eje largo (90 mm) vertical. Ocupa 60 mm en X y sólo 6 mm en Y.
    #   - Floor general a z=8 (2 mm) para apoyar también la electrónica baja.
    #   - Paredes laterales a x = ±31 desde z=10 hasta z=100 (90 mm de alto).
    #   - Retén trasero a y = -DEPTH/2 + WALL + 6 + 0.5 (deja 6.5 mm de hueco
    #     desde la cara frontal interior, ajuste para la batería de 6 mm).
    #   - Puente superior a z=98 con paso de cables en el centro.
    BAT_T = 6.0          # grosor real
    BAT_SLACK = 0.8      # holgura total entre batería y paredes
    bat_floor = Box(
        WIDTH_CENTRAL - 2 * WALL,
        DEPTH - 2 * WALL,
        2.0,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((0, 0, 8.0)))
    p = p + bat_floor

    # Paredes laterales de la cuna (retención X): 2 mm de grosor, 90 mm altas.
    # Batería apoyada contra la cara INTERIOR de la pared trasera.
    y_bat_center = DEPTH / 2 - WALL - (BAT_T + BAT_SLACK) / 2
    for sx in (-1, 1):
        wall_bat = Box(
            2.0,
            BAT_T + BAT_SLACK,
            BAT_Z1 - BAT_Z0,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((
            sx * (BAT_W / 2 + 1.0 + BAT_SLACK / 2),
            y_bat_center,
            BAT_Z0,
        )))
        p = p + wall_bat

    # Retén frontal: placa fina que impide que la batería se salga hacia
    # delante (la tapa trasera la sujeta por detrás al cerrar).
    y_retainer = y_bat_center - (BAT_T + BAT_SLACK) / 2
    bat_back = Box(
        BAT_W + 4.0,
        1.5,
        BAT_Z1 - BAT_Z0 - 10.0,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((0, y_retainer, BAT_Z0)))
    p = p + bat_back
    # Ventana central en el retén frontal para ver/agarrar la batería
    bat_window = Box(
        30.0, 3.0, 40.0,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((0, y_retainer, BAT_Z0 + 15.0)))
    p = p - bat_window

    # Puente superior (retiene la batería por arriba) a z=BAT_Z1-2 con
    # paso central de cables (12×5) para los hilos rojo/negro.
    bat_top = Box(
        BAT_W + 4.0,
        BAT_T + BAT_SLACK,
        2.0,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((
        0,
        y_bat_center,
        BAT_Z1 - 2.0,
    )))
    p = p + bat_top
    # Paso de cables en el puente superior
    cable_slot = Box(
        12.0, BAT_T + BAT_SLACK + 1.0, 3.0,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((
        0,
        y_bat_center,
        BAT_Z1 - 2.0 - 0.5,
    )))
    p = p - cable_slot

    # -------------------------------------------------------------------
    # COMPARTIMENTOS INTERIORES (tabiques horizontales con paso de cables)
    # -------------------------------------------------------------------
    # El interior se organiza en zonas apiladas separadas por tabiques
    # de 2 mm con pasacables central 20×15 y dos canaletas 8×8:
    #   z=10..40    → ALTAVOZ rectangular 70×30×15 mm (frontal, área baja)
    #   z=30..120   → BATERÍA 60×90×6 mm (de pie, pegada a la trasera)
    #   z=128..158  → ZONA DE SERVOS (eje z=145, cuna en paredes laterales)
    #   z=162..206  → OLED
    #   z=207..230  → ToF / Cam / XIAO (cradle propio)
    def _divider(z: float, label: str) -> None:
        nonlocal p
        floor = Box(
            WIDTH_CENTRAL - 2 * WALL,
            DEPTH - 2 * WALL,
            2.0,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((0, 0, z)))
        p = p + floor
        # paso central de cables
        cp = Box(
            20.0, 15.0, 4.0,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((0, 0, z - 1.0)))
        p = p - cp
        # canal vertical grande en el lado DERECHO (rompe cada divisor
        # creando un pasacables continuo de arriba a abajo para meter
        # mazos ya conectorizados sin desoldar)
        right_ch = Box(
            14.0, DEPTH - 2 * WALL, 4.0,
            align=(Align.MAX, Align.CENTER, Align.MIN),
        ).locate(Location((
            WIDTH_CENTRAL / 2 - WALL - 0.5,
            0,
            z - 1.0,
        )))
        p = p - right_ch

    _divider(123.0, "bat->servos")       # techo batería (top=125) / suelo zona servos
    _divider(160.0, "servos->oled")      # techo zona servos / suelo OLED
    _divider(208.0, "oled->camtof")      # techo OLED

    # -------------------------------------------------------------------
    # CAJITA / CRADLE DEL XIAO ESP32-S3 SENSE (press-fit, sin tornillos)
    #   - PCB XIAO ESP32-S3 Sense: 21 × 17.8 mm
    #   - Stack apilado (XIAO + expansion Sense con cámara): 21 × 17.8 × 15 mm
    # Orientación elegida: USB-C apuntando a +Z (sale por tapa superior).
    #   → X = 17.8 (ancho PCB)
    #   → Y = 15.0 (grosor total del stack, incluye Sense)
    #   → Z = 21.0 (alto PCB, USB-C arriba)
    # El stack entra por arriba y se sujeta por fricción (holgura 0.2 mm/lado).
    # La tapa superior, al cerrarse, presiona el borde superior del PCB
    # impidiendo que suba. Debajo, un hueco rectangular deja pasar el flex
    # de la cámara y los headers hacia el interior del chasis.
    XIAO_W = 17.8
    XIAO_D = 15.0
    XIAO_H = 21.0
    XIAO_SLACK = 0.4          # holgura TOTAL (0.2 por lado)
    CRADLE_WALL = 2.0
    CRADLE_FLOOR = 2.0
    # Tope superior del stack justo bajo la tapa (z=230):
    xiao_z_top = HEIGHT - 4.0              # 230 mm
    xiao_z_bot = xiao_z_top - XIAO_H       # 209 mm (borde inferior PCB)
    cradle_z_bot = xiao_z_bot - CRADLE_FLOOR  # 207 mm (base exterior cajita)

    # Caja exterior de la cajita
    cradle_ext = Box(
        XIAO_W + XIAO_SLACK + 2 * CRADLE_WALL,
        XIAO_D + XIAO_SLACK + 2 * CRADLE_WALL,
        XIAO_H + CRADLE_FLOOR,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((0, 0, cradle_z_bot)))
    p = p + cradle_ext

    # Hueco interior donde encaja el stack (abierto por arriba)
    cradle_pocket = Box(
        XIAO_W + XIAO_SLACK,
        XIAO_D + XIAO_SLACK,
        XIAO_H + 2.0,   # +2 para que atraviese la cara superior
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((0, 0, xiao_z_bot)))
    p = p - cradle_pocket

    # Paso de flex y headers por el suelo de la cajita (12 × 8 mm)
    cradle_cable = Box(
        12.0, 8.0, CRADLE_FLOOR + 2.0,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((0, 0, cradle_z_bot - 1.0)))
    p = p - cradle_cable

    # Dos rebajes laterales para poder pellizcar y sacar el XIAO con los dedos
    for sx in (-1, 1):
        finger_cut = Box(
            CRADLE_WALL + 1.0,
            (XIAO_D + XIAO_SLACK) * 0.6,
            8.0,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((
            sx * (XIAO_W / 2 + XIAO_SLACK / 2 + CRADLE_WALL / 2),
            0,
            xiao_z_top - 8.0 + 0.5,
        )))
        p = p - finger_cut

    # -------------------------------------------------------------------
    # SNAP-FIT DE LA TAPA SUPERIOR (sin tornillos)
    # -------------------------------------------------------------------
    # 4 ranuras en las caras interiores del borde superior del bloque
    # donde claven las 4 barbas de las lengüetas de la tapa.
    H_LID_SEAT = HEIGHT - 4.0     # Z del asiento de la tapa
    for side in ("front", "back", "left", "right"):
        if side == "front":
            pos = (0, -DEPTH / 2 + WALL - 0.1, H_LID_SEAT - 3.5)
            sz = (TOP_LID_TAB_W + 0.4, 1.2, 1.6)
        elif side == "back":
            pos = (0, +DEPTH / 2 - WALL + 0.1, H_LID_SEAT - 3.5)
            sz = (TOP_LID_TAB_W + 0.4, 1.2, 1.6)
        elif side == "left":
            pos = (-WIDTH_CENTRAL / 2 + WALL - 0.1, 0, H_LID_SEAT - 3.5)
            sz = (1.2, TOP_LID_TAB_W + 0.4, 1.6)
        else:
            pos = (+WIDTH_CENTRAL / 2 - WALL + 0.1, 0, H_LID_SEAT - 3.5)
            sz = (1.2, TOP_LID_TAB_W + 0.4, 1.6)
        slot = Box(
            sz[0], sz[1], sz[2],
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location(pos))
        p = p - slot

    # -------------------------------------------------------------------
    # RETENCIÓN OLED (sin tornillos): 2 clips flexibles que pellizcan el PCB
    # contra el reborde frontal.
    # -------------------------------------------------------------------
    oled_cy = (OLED_Z0 + OLED_Z1) / 2
    for sz_sign in (-1, 1):
        clip = Box(
            14.0, 3.0, 2.0,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location((
            0,
            -DEPTH / 2 + WALL + OLED_PCB_DEPTH + 1.5,
            oled_cy + sz_sign * (OLED_PCB_H / 2 + 1.0),
        )))
        p = p + clip
        # barba de retención (presiona el PCB hacia -Y)
        barb = Box(
            14.0, 1.0, 1.0,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location((
            0,
            -DEPTH / 2 + WALL + OLED_PCB_DEPTH + 0.5,
            oled_cy + sz_sign * (OLED_PCB_H / 2 - 0.5),
        )))
        p = p + barb

    # -------------------------------------------------------------------
    # DETALLES ESTÉTICOS (estilo TARS de la película)
    # · Líneas horizontales cada 39 mm (separación modular).
    # · Falso separador vertical en la ventana OLED para simular 2 pantallas.
    # · "TARS" vertical en el panel central + patrón de puntos tipo braille.
    # -------------------------------------------------------------------
    p = engrave_panel_lines_modular(p, WIDTH_CENTRAL, DEPTH, units=6)
    # Ranuras VERTICALES en TODAS las caras exteriores — patrón principal
    # TARS (listonado vertical). En el frontal, las ranuras que crucen la
    # pantalla OLED no pasa nada porque la pantalla ya está recortada.
    p = engrave_vertical_slats(
        p, WIDTH_CENTRAL, DEPTH, HEIGHT,
        pitch=6.5, line_thickness=0.8, depth=0.6, z_margin=3.0,
        faces=("back", "left", "right"),
    )
    # En el frontal: ranuras verticales SÓLO en las bandas laterales,
    # dejando libre el centro (columna de OLED / TARS / braille).
    try:
        front_slat_pitch = 5.5
        front_slat_thk = 0.8
        front_slat_depth = 0.6
        front_center_clear = 44.0   # ancho libre en el centro
        front_zmin, front_zmax = 3.0, HEIGHT - 3.0
        z_len_f = front_zmax - front_zmin
        z_cf = (front_zmin + front_zmax) / 2
        fb_cut = Box(front_slat_thk, front_slat_depth * 2, z_len_f,
                     align=(Align.CENTER, Align.CENTER, Align.CENTER))
        x0 = front_center_clear / 2
        x1 = WIDTH_CENTRAL / 2 - 1.5
        x = x0
        while x <= x1:
            p = p - fb_cut.locate(Location((+x, -DEPTH / 2, z_cf)))
            p = p - fb_cut.locate(Location((-x, -DEPTH / 2, z_cf)))
            x += front_slat_pitch
    except Exception as e:
        print(f"  ! ranuras frontales saltadas: {type(e).__name__}: {e}")

    # Paneles de rayado horizontal flanqueando la OLED (rejillas TARS)
    oled_cy = (OLED_Z0 + OLED_Z1) / 2
    try:
        hatch_panel_w = 10.0
        hatch_z0 = oled_cy - OLED_H / 2 - 1.0
        hatch_z1 = oled_cy + OLED_H / 2 + 1.0
        hatch_x = (OLED_W / 2) + 1.0 + hatch_panel_w / 2
        for sx in (-1, +1):
            p = engrave_hatch_panel(
                p, sx * hatch_x, hatch_z0, hatch_z1,
                hatch_panel_w, DEPTH,
                pitch=1.1, line_thickness=0.5, depth=0.5,
            )
    except Exception as e:
        print(f"  ! rejillas OLED saltadas: {type(e).__name__}: {e}")

    # Separador vertical entre las 2 "pantallas" — DESACTIVADO: el usuario
    # lo pintará directamente en la pantalla por software.
    # (bloque eliminado a propósito)

    # --- "TARS" vertical (letras apiladas, cada una legible) ---------------
    # Letras GRANDES, centradas en el frontal, debajo de las pantallas.
    try:
        letras = "TARS"
        tars_size = 14.0                    # letra grande (como en la peli)
        tars_step = 17.0                    # separación entre letras
        tars_x = -8.0                       # ligeramente a la izquierda del centro
        tars_z_top = 105.0                  # z de la 1ª letra (arriba)
        for i, ch in enumerate(letras):
            with BuildSketch(Plane.XZ) as sk:
                with Locations((tars_x, tars_z_top - i * tars_step)):
                    Text(ch, font_size=tars_size,
                         align=(Align.CENTER, Align.CENTER))
            carve = extrude(sk.sketch, amount=1.2)
            carve = carve.rotate(Axis.Z, 180)
            carve = carve.moved(Location((0, -DEPTH / 2 + 1.1, 0)))
            p = p - carve
    except Exception as e:
        print(f"  ! texto TARS saltado: {type(e).__name__}: {e}")

    # --- Puntos tipo braille a la derecha del texto TARS ------------------
    # Rejilla 2 columnas × 4 filas de círculos rebajados, a la derecha de
    # las letras grandes (como en la peli).
    try:
        dot_d = 3.2
        dot_depth = 1.0
        dot_dx = 5.0
        dot_dz = 8.5
        dot_x0 = 12.0                       # a la derecha del texto
        dot_z0 = tars_z_top + 3.0
        for col in range(2):
            for row in range(4):
                dx = dot_x0 + col * dot_dx
                dz = dot_z0 - row * dot_dz
                dot = Cylinder(
                    dot_d / 2, dot_depth * 2,
                    align=(Align.CENTER, Align.CENTER, Align.CENTER),
                    rotation=(90, 0, 0),
                ).locate(Location((dx, -DEPTH / 2 + dot_depth, dz)))
                p = p - dot
    except Exception:
        pass

    return p


# =============================================================================
# BRAZO LATERAL (39 × 39 × 351)
# =============================================================================


def make_brazo(side: str) -> Part:
    """side: 'left' or 'right'. Diferencia: agujero del horn + pivote en la cara interior."""
    # Los brazos son CERRADOS por arriba (no hay tapa desmontable). Así la
    # cara superior queda plana y monolítica, igual que el TARS de la peli.
    p = hollow_box(WIDTH_ARM, DEPTH, HEIGHT, wall=WALL, open_top=False)

    # Cara interior: la que da al bloque central.
    # Si side == 'left'  → cara interior está en +X (el brazo está a la izquierda)
    # Si side == 'right' → cara interior está en -X
    inner_face = "right" if side == "left" else "left"

    # (a) PRESS-FIT del brazo sobre el eje estriado del servo.
    #     NO se usa el horn de plástico. El propio brazo se monta directamente
    #     sobre el eje dorado estriado — los dientes de latón muerden el PLA
    #     y crean un acople antigiro permanente.
    x_inner = WIDTH_ARM / 2 if inner_face == "right" else -WIDTH_ARM / 2
    sgn = 1 if inner_face == "right" else -1

    # Refuerzo cilíndrico por dentro del brazo (aporta material alrededor
    # del press-fit para que no raje al insertarlo). Va pegado a la pared
    # interior del brazo, apuntando hacia el interior hueco.
    boss = Cylinder(
        SPLINE_BOSS_D / 2,
        SPLINE_BOSS_H,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
        rotation=(0, -sgn * 90, 0),
    ).locate(Location((x_inner - sgn * WALL, 0, SERVO_AXIS_Z)))
    p = p + boss

    # Agujero ciego con ø press-fit para el eje estriado (por dentro).
    spline_hole = Cylinder(
        SPLINE_D / 2,
        SPLINE_DEPTH,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
        rotation=(0, -sgn * 90, 0),
    ).locate(Location((x_inner - sgn * WALL, 0, SERVO_AXIS_Z)))
    p = p - spline_hole

    # Paso para el tornillo M2.5 que trae el servo, con avellanado
    # EN LA CARA EXTERIOR del brazo (así el tornillo se aprieta desde fuera
    # y la cabeza queda embutida — estéticamente limpio).
    m25_through = Cylinder(
        SCREW_M25_CLEARANCE_D / 2,
        WALL + SPLINE_BOSS_H + 2.0,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
        rotation=(0, 90, 0),
    ).locate(Location((x_inner, 0, SERVO_AXIS_Z)))
    p = p - m25_through
    m25_head = Cylinder(
        SCREW_M25_HEAD_D / 2,
        2.5,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
        rotation=(0, sgn * 90, 0),
    ).locate(Location((x_inner, 0, SERVO_AXIS_Z)))
    p = p - m25_head

    # Nervios internos de rigidez
    for z_rib in [100, 230]:
        rib = Box(
            WIDTH_ARM - 2 * WALL,
            DEPTH - 2 * WALL,
            2.0,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((0, 0, z_rib)))
        p = p + rib

    # (TARS no tiene ventilación lateral visible)

    # Líneas de panel horizontales cada 39 mm (juntas entre "bloques")
    p = engrave_panel_lines_modular(p, WIDTH_ARM, DEPTH, units=6)
    # Ranuras VERTICALES — el listonado característico de TARS recorre todo
    # el cuerpo de arriba a abajo en las 4 caras.
    p = engrave_vertical_slats(
        p, WIDTH_ARM, DEPTH, HEIGHT,
        pitch=6.5, line_thickness=0.8, depth=0.6, z_margin=3.0,
        faces=("front", "back", "left", "right"),
    )

    return p


# =============================================================================
# TAPA TRASERA (78 × 3 × 351) — acceso completo al interior del central
# =============================================================================


def make_tapa_trasera() -> Part:
    """Tapa trasera FLUSH: encaja dentro del marco trasero del bloque central,
    quedando a ras con las caras traseras de los brazos (sin hueco visible).

    Mecánica: panel rectangular con 4 clips cantilever (2 arriba, 2 abajo) que
    salen por la cara interior y hacen *click* en muescas del marco. Se
    desmonta empujando los clips superiores hacia abajo con una uña/espátula
    fina por la rendija de 0.2 mm que queda entre tapa y marco.
    """
    TAPA_T_TOP = 4.0
    H_CENTRAL = HEIGHT - TAPA_T_TOP

    LID_CLEAR = 0.4   # holgura total (0.2 por lado)
    LID_W = WIDTH_CENTRAL - 2 * WALL - LID_CLEAR
    LID_H = H_CENTRAL - 2 * WALL - LID_CLEAR
    LID_BARB_D = 1.0
    CLIP_ARM_LEN = 8.0
    CLIP_ARM_T = 1.4      # grosor del brazo flex (en Y)
    CLIP_ARM_H = 3.0      # alto del brazo flex (en Z)

    # Panel principal (orientado para que +Y sea la cara EXTERIOR, -Y interior).
    # Lo construyo centrado en origen (CENTER, CENTER, CENTER) y luego al
    # posicionarlo quedará con su centro en y=DEPTH/2-REAR_LID_T/2, z=centro
    # del marco interior.
    with BuildPart() as tr:
        Box(
            LID_W,
            REAR_LID_T,
            LID_H,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        if FILLET_EDGE > 0:
            fillet(tr.edges().filter_by(Axis.Y), radius=FILLET_EDGE)
    p = tr.part

    # --- Clips cantilever SUPERIORES (2) ---
    # Brazo horizontal que sale de la cara interior (-Y), cerca del borde
    # superior. Al final del brazo, un barb que sobresale hacia +Z encaja
    # en la muesca del marco superior.
    for cx in REAR_LID_CLIP_X:
        arm_y_center = -REAR_LID_T / 2 - CLIP_ARM_LEN / 2
        arm_z_center = LID_H / 2 - CLIP_ARM_H / 2 - 0.2
        arm = Box(
            REAR_LID_SNAP_W,
            CLIP_ARM_LEN,
            CLIP_ARM_T,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location((cx, arm_y_center, arm_z_center + CLIP_ARM_H / 2 - CLIP_ARM_T / 2)))
        p = p + arm
        # Barba hacia +Z al final del brazo
        barb = Box(
            REAR_LID_SNAP_W,
            2.0,
            LID_BARB_D,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).locate(Location((
            cx,
            -REAR_LID_T / 2 - CLIP_ARM_LEN + 1.0,
            arm_z_center + CLIP_ARM_H / 2 - CLIP_ARM_T + 0.01,
        )))
        p = p + barb

    # --- Clips cantilever INFERIORES (2) ---
    for cx in REAR_LID_CLIP_X:
        arm_y_center = -REAR_LID_T / 2 - CLIP_ARM_LEN / 2
        arm_z_center = -LID_H / 2 + CLIP_ARM_H / 2 + 0.2
        arm = Box(
            REAR_LID_SNAP_W,
            CLIP_ARM_LEN,
            CLIP_ARM_T,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location((cx, arm_y_center, arm_z_center - CLIP_ARM_H / 2 + CLIP_ARM_T / 2)))
        p = p + arm
        # Barba hacia -Z al final del brazo
        barb = Box(
            REAR_LID_SNAP_W,
            2.0,
            LID_BARB_D,
            align=(Align.CENTER, Align.CENTER, Align.MAX),
        ).locate(Location((
            cx,
            -REAR_LID_T / 2 - CLIP_ARM_LEN + 1.0,
            arm_z_center - CLIP_ARM_H / 2 + CLIP_ARM_T - 0.01,
        )))
        p = p + barb

    # --- 2 rails laterales (izq/dcha) que encajan en las muescas laterales
    #     del marco — aportan sujeción horizontal y anti-combeo ---
    LID_CENTER_Z = WALL + LID_H / 2 + LID_CLEAR / 2   # no se usa aquí, sólo referencia
    for rz_abs in REAR_LID_RAIL_Z:
        # rz_abs está en coords globales del bloque; lo paso a coords locales
        # de la tapa. Tapa centrada en z=WALL + LID_H/2 + LID_CLEAR/2.
        lid_z_center = WALL + LID_H / 2 + LID_CLEAR / 2
        rz_local = rz_abs - lid_z_center
        for sx in (-1, 1):
            rail = Box(
                LID_BARB_D,
                2.4,
                9.6,
                align=(Align.CENTER, Align.MIN, Align.CENTER),
            ).locate(Location((
                sx * (LID_W / 2 - 0.01),
                -REAR_LID_T / 2,
                rz_local,
            )))
            p = p + rail

    # Interruptor on/off rocker ø6.5 mm (accesible desde fuera).
    sw = Cylinder(
        SWITCH_HOLE_D / 2,
        REAR_LID_T + 2,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
        rotation=(90, 0, 0),
    ).locate(Location((0, 0, SWITCH_Z - (WALL + LID_H / 2 + LID_CLEAR / 2))))
    p = p - sw

    # Muesca de paso de cables en el borde INFERIOR (abierta por el canto).
    cable_notch = Box(
        12.0,
        REAR_LID_T + 4.0,
        5.0,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).locate(Location((0, 0, -LID_H / 2 - 0.1)))
    p = p - cable_notch

    return p


# =============================================================================
# TAPA SUPERIOR (156 × 39 × 4)
# =============================================================================


def make_tapa_superior() -> Part:
    """Tapa superior snap-fit (sin tornillos). SÓLO cubre el bloque central (78×39).
    Por debajo tiene un tongue perimetral de 1.5 mm que entra friccionando en
    el interior + 4 lengüetas con barba que clavan en 4 pockets."""
    TAPA_T = TOP_LID_T
    with BuildPart() as tp:
        Box(
            WIDTH_CENTRAL,
            DEPTH,
            TAPA_T,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        if FILLET_EDGE > 0:
            fillet(tp.edges().filter_by(Axis.Z), radius=FILLET_EDGE)
    p = tp.part

    # Tongue perimetral (1.5 mm de alto, 0.3 mm más estrecho que el interior)
    tongue_outer = Box(
        WIDTH_CENTRAL - 2 * WALL - 0.3,
        DEPTH - 2 * WALL - 0.3,
        TOP_LID_TONGUE,
        align=(Align.CENTER, Align.CENTER, Align.MAX),
    ).locate(Location((0, 0, 0)))
    p = p + tongue_outer
    # Vaciar el interior del tongue (hueco para el XIAO y cables)
    tongue_hole = Box(
        WIDTH_CENTRAL - 2 * WALL - 6.0,
        DEPTH - 2 * WALL - 6.0,
        TOP_LID_TONGUE + 1,
        align=(Align.CENTER, Align.CENTER, Align.MAX),
    ).locate(Location((0, 0, 0.1)))
    p = p - tongue_hole

    # 4 lengüetas snap en el centro de cada lado (X ±, Y ±)
    tab_positions = [
        (0, -DEPTH / 2 + WALL + 0.5, "front"),
        (0, +DEPTH / 2 - WALL - 0.5, "back"),
        (-WIDTH_CENTRAL / 2 + WALL + 0.5, 0, "left"),
        (+WIDTH_CENTRAL / 2 - WALL - 0.5, 0, "right"),
    ]
    for tx, ty, side in tab_positions:
        if side in ("front", "back"):
            tab = Box(
                TOP_LID_TAB_W, 1.5, TOP_LID_TAB_H,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
            ).locate(Location((tx, ty, 0)))
            barb_y = ty + (0.9 if side == "front" else -0.9)
            barb = Box(
                TOP_LID_TAB_W, 1.0, 1.2,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
            ).locate(Location((tx, barb_y, -TOP_LID_TAB_H + 1.5)))
        else:
            tab = Box(
                1.5, TOP_LID_TAB_W, TOP_LID_TAB_H,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
            ).locate(Location((tx, ty, 0)))
            barb_x = tx + (0.9 if side == "left" else -0.9)
            barb = Box(
                1.0, TOP_LID_TAB_W, 1.2,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
            ).locate(Location((barb_x, ty, -TOP_LID_TAB_H + 1.5)))
        p = p + tab
        p = p + barb

    # Ranura USB-C del XIAO (10 × 5 mm)
    slot = Box(10, 5, TAPA_T + 2, align=(Align.CENTER, Align.CENTER, Align.MIN)).locate(
        Location((0, 0, -1))
    )
    p = p - slot
    return p


# =============================================================================
# SOPORTE DE SERVOS — refuerzo rígido entre los dos servos
# =============================================================================
# Mantiene las caras interiores de los dos ES08MDII perfectamente alineadas
# y anula cualquier flexión del bloque central a la altura del eje de giro.
# Se inserta desde arriba (con la tapa superior fuera) y queda encajado a
# presión entre ambos servos, apoyado en el suelo/techo de sus cunas.
#
# Geometría interna (referencia):
#   Cara interior de cada servo (eje X):  x = ±(WIDTH_CENTRAL/2 - WALL - SERVO_BODY_H - SERVO_SLACK)
#                                          = ±(39 - 3 - 11.6 - 0.5) = ±23.9
#   Hueco libre entre servos              : 47.8 mm
#   Cuerpo del servo en Y                 : [-11.75, +11.75]  (cables salen por +Y)
#   Cuerpo del servo en Z                 : [130.75, 155.25]  (centro z = 143)
# =============================================================================

def make_soporte_servos() -> Part:
    """Soporte en forma de MANCUERNA que abraza ambos servos.

    Anatomía:
      - Puente central (viga)         : rellena el hueco entre los dos servos.
      - Cabezales rectangulares (×2)  : en cada extremo del puente, con un
                                        BOLSILLO rectangular (24×25 mm) que
                                        encaja sobre la cara INTERIOR del
                                        cuerpo del servo. La forma rectangular
                                        del bolsillo es la que IMPIDE el giro
                                        del servo al aplicar par (interlock
                                        geométrico, no depende de fricción).
    """
    # --- Dimensiones derivadas de las constantes del servo -----------------
    # Hueco libre X entre caras interiores de los servos
    gap_servos_x = WIDTH_CENTRAL - 2 * WALL - 2 * (SERVO_BODY_H + SERVO_SLACK)
    # --- Viga (puente) entre servos ---------------------------------------
    # Deja 4 mm por cada lado para los cabezales con bolsillo.
    head_x = 4.0                         # espesor X de cada cabezal
    pocket_depth = 2.5                   # profundidad del bolsillo (la cara
                                         # interior del servo entra 2.5 mm)
    beam_x = gap_servos_x - 2 * head_x + 2 * pocket_depth - 0.2
    beam_y = 18.0                        # menos que el servo (23.5) para dejar
                                         # paso libre al lado +Y (cables)
    beam_z = SERVO_BODY_D - 4.0          # ~20.5 mm, cabe en la altura libre
    # --- Cabezales rectangulares (enganche antigiro) ----------------------
    head_y = SERVO_BODY_W + 4.0          # 27.5 mm — 2 mm de reborde alrededor
    head_z = SERVO_BODY_D + 4.0          # 28.5 mm
    # Bolsillo interior del cabezal (se "encaja" la cara interior del servo)
    pocket_y = SERVO_BODY_W + SERVO_SLACK + 0.1   # 24.1 mm (holgura inserción)
    pocket_z = SERVO_BODY_D + SERVO_SLACK + 0.1   # 25.1 mm
    # El cabezal va centrado en el servo; la viga está desplazada en Y
    # para liberar +Y (cables).
    y_beam_offset = -2.75                # viga (−11.75 .. 8.25)
    # Centros Z/Y del cuerpo del servo
    z_center = SERVO_AXIS_Z - 2.0        # igual que la cuna del servo

    # --- Construcción: viga + 2 cabezales ---------------------------------
    beam = Box(
        beam_x, beam_y, beam_z,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    ).locate(Location((0, y_beam_offset, 0)))
    p = beam
    for sx in (-1, 1):
        # Posición del cabezal: su cara EXTERIOR (la que da al servo) queda a
        # x = ±(gap_servos_x/2 − 0.1) ≈ ±23.8 (0.1 mm de holgura total).
        head_x_outer = gap_servos_x / 2 - 0.1
        head_cx = sx * (head_x_outer - head_x / 2)
        head = Box(
            head_x, head_y, head_z,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location((head_cx, 0, 0)))
        # Bolsillo rectangular en la cara exterior del cabezal — aquí encaja
        # la cara interior del servo (interlock antigiro).
        pocket = Box(
            pocket_depth * 2,      # se abre hacia afuera; 2× asegura corte limpio
            pocket_y, pocket_z,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).locate(Location((
            sx * (head_x_outer - pocket_depth / 2),  # centro del bolsillo
            0, 0,
        )))
        head = head - pocket
        p = p + head

    # Aligeramiento opcional en la viga (ventana pasante en Y — pasacables).
    window = Box(
        max(beam_x - 20.0, 0.1), beam_y + 2.0, beam_z - 10.0,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    ).locate(Location((0, y_beam_offset, 0)))
    p = p - window

    # Chaflán en las aristas extremas para facilitar la inserción vertical
    # (el soporte entra desde arriba cuando la tapa superior está fuera).
    try:
        ends = [e for e in p.edges()
                if abs(abs(e.center().X) - (gap_servos_x / 2 - 0.1)) < 0.05]
        if ends:
            p = fillet(ends, radius=0.8)
    except Exception:
        pass

    # Llevar al sitio de montaje
    p = p.locate(Location((0, 0, z_center)))
    return p


# =============================================================================
# ENSAMBLAJE Y EXPORTACIÓN
# =============================================================================


def build_all() -> dict[str, Part]:
    print("[build123d] Generando bloque_central ...")
    central = make_bloque_central()

    print("[build123d] Generando tapa_trasera ...")
    trasera = make_tapa_trasera()

    print("[build123d] Generando brazo_izquierdo ...")
    brazo_izq = make_brazo("left")

    print("[build123d] Generando brazo_derecho ...")
    brazo_der = make_brazo("right")

    print("[build123d] Generando tapa_superior ...")
    tapa = make_tapa_superior()

    print("[build123d] Generando soporte_servos ...")
    soporte = make_soporte_servos()

    result = {
        "bloque_central": central,
        "tapa_trasera": trasera,
        "brazo_izquierdo": brazo_izq,
        "brazo_derecho": brazo_der,
        "tapa_superior": tapa,
        "soporte_servos": soporte,
    }
    # Normalizar: tras muchos booleanos, algunas piezas pueden ser ShapeList
    # en vez de Part. Convertimos todo a Part antes de continuar.
    result = {name: _as_part_global(part) for name, part in result.items()}
    # Asignar color a cada pieza (visible en OCP Viewer y embebido en el 3mf)
    for name, part in result.items():
        try:
            part.color = Color(*COLORS[name])
        except Exception:
            pass
    return result


def assembly(parts: dict[str, Part]) -> Compound:
    """Posiciona las 5 piezas como quedarían ensambladas (solo para preview/3mf)."""
    x_izq = -(WIDTH_CENTRAL / 2 + ARM_GAP + WIDTH_ARM / 2)
    x_der = +(WIDTH_CENTRAL / 2 + ARM_GAP + WIDTH_ARM / 2)

    placed = [
        parts["bloque_central"].locate(Location((0, 0, 0))),
        parts["tapa_trasera"].locate(Location((0, DEPTH / 2 - REAR_LID_T / 2, (HEIGHT - 4.0) / 2))),
        parts["brazo_izquierdo"].locate(Location((x_izq, 0, 0))),
        parts["brazo_derecho"].locate(Location((x_der, 0, 0))),
        parts["tapa_superior"].locate(Location((0, 0, HEIGHT - 4.0))),
    ]
    return Compound(label="TARS", children=placed)


def _consolidate_3mf_single_object(path: Path) -> None:
    """Colapsa un 3MF de una sola pieza en UN único ``<object>`` con UN único
    ``<item>`` en ``<build>``, aplicando los transforms de build a los
    vértices de cada malla.

    Necesario porque Bambu Studio detecta varios ``<item>`` a alturas
    distintas como "multi-part object" (aunque sea una única pieza
    imprimible con cavidades/insertos internos desconectados).
    """
    if not path.exists():
        return
    try:
        with zipfile.ZipFile(path, "r") as zin:
            members = {n: zin.read(n) for n in zin.namelist()}
    except Exception:
        return
    model_key = "3D/3dmodel.model"
    if model_key not in members:
        return

    xml = members[model_key].decode("utf-8", "ignore")

    # Localizar items del build y su transform
    build_items: list[tuple[str, str | None]] = []
    for item_m in re.finditer(r'<item\s+([^/]*?)/>', xml):
        attrs = item_m.group(1)
        oid_m = re.search(r'objectid="(\d+)"', attrs)
        if not oid_m:
            continue
        tf_m = re.search(r'transform="([^"]*)"', attrs)
        build_items.append((oid_m.group(1), tf_m.group(1) if tf_m else None))
    if len(build_items) <= 1:
        return  # ya está consolidado

    # Mapa objectid -> ruta de componente (si la hay)
    comp_map: dict[str, tuple[str, str]] = {}
    for obj_match in re.finditer(
        r'<object\s+id="(\d+)"[^>]*type="model"[^>]*>(.*?)</object>',
        xml,
        flags=re.DOTALL,
    ):
        oid = obj_match.group(1)
        body = obj_match.group(2)
        comp = re.search(
            r'<component\s+p:path="([^"]+)"\s+objectid="(\d+)"',
            body,
        )
        if comp:
            comp_map[oid] = (comp.group(1), comp.group(2))

    def _parse_tf(s: str | None) -> tuple[float, ...]:
        if not s:
            return (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)
        try:
            vals = tuple(float(x) for x in s.split())
            if len(vals) == 12:
                return vals
        except ValueError:
            pass
        return (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)

    def _apply_tf(tf: tuple[float, ...], x: float, y: float, z: float) -> tuple[float, float, float]:
        # 3MF transform is column-major 4x3: [a b c  d e f  g h i  tx ty tz]
        # new = M * v + t, with M rows (a,d,g)(b,e,h)(c,f,i)
        a, b, c, d, e, f, g, h, i, tx, ty, tz = tf
        nx = a * x + d * y + g * z + tx
        ny = b * x + e * y + h * z + ty
        nz = c * x + f * y + i * z + tz
        return nx, ny, nz

    all_verts: list[tuple[float, float, float]] = []
    all_tris: list[tuple[int, int, int]] = []

    for oid, tf_s in build_items:
        tf = _parse_tf(tf_s)
        if oid not in comp_map:
            continue
        comp_path, _comp_oid = comp_map[oid]
        mem_key = comp_path.lstrip("/")
        if mem_key not in members:
            continue
        sub_xml = members[mem_key].decode("utf-8", "ignore")
        # Extraer vértices
        verts_local: list[tuple[float, float, float]] = []
        for vm in re.finditer(r'<vertex\s+x="([^"]+)"\s+y="([^"]+)"\s+z="([^"]+)"\s*/>', sub_xml):
            vx = float(vm.group(1)); vy = float(vm.group(2)); vz = float(vm.group(3))
            verts_local.append(_apply_tf(tf, vx, vy, vz))
        base_idx = len(all_verts)
        all_verts.extend(verts_local)
        # Triángulos
        for tm in re.finditer(r'<triangle\s+v1="(\d+)"\s+v2="(\d+)"\s+v3="(\d+)"', sub_xml):
            v1 = int(tm.group(1)) + base_idx
            v2 = int(tm.group(2)) + base_idx
            v3 = int(tm.group(3)) + base_idx
            all_tris.append((v1, v2, v3))

    if not all_verts or not all_tris:
        return

    # Construir un nuevo 3dmodel.model con un único objeto+mesh+item
    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">'
    )
    lines.append(' <resources>')
    lines.append('  <object id="1" type="model">')
    lines.append('   <mesh>')
    lines.append('    <vertices>')
    for vx, vy, vz in all_verts:
        lines.append(f'     <vertex x="{vx:.6f}" y="{vy:.6f}" z="{vz:.6f}"/>')
    lines.append('    </vertices>')
    lines.append('    <triangles>')
    for v1, v2, v3 in all_tris:
        lines.append(f'     <triangle v1="{v1}" v2="{v2}" v3="{v3}"/>')
    lines.append('    </triangles>')
    lines.append('   </mesh>')
    lines.append('  </object>')
    lines.append(' </resources>')
    lines.append(' <build>')
    lines.append('  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0" printable="1"/>')
    lines.append(' </build>')
    lines.append('</model>')

    new_xml = "\n".join(lines).encode("utf-8")

    # Eliminar los object_*.model viejos y reescribir model principal
    new_members: dict[str, bytes] = {}
    for k, v in members.items():
        if k.startswith("3D/Objects/") and k.endswith(".model"):
            continue
        new_members[k] = v
    new_members[model_key] = new_xml

    # Limpiar _rels que apuntaban a los object_*.model
    rels_key = "3D/_rels/3dmodel.model.rels"
    if rels_key in new_members:
        rels = new_members[rels_key].decode("utf-8", "ignore")
        rels = re.sub(
            r'<Relationship[^/]*Target="[^"]*Objects/object_\d+\.model"[^/]*/>',
            "",
            rels,
        )
        new_members[rels_key] = rels.encode("utf-8")

    tmp = path.with_suffix(".3mf.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, d in new_members.items():
            zout.writestr(n, d)
    shutil.move(str(tmp), str(path))


def _inject_3mf_color(path: Path, rgba: tuple[float, float, float, float],
                       filament_slot: int = 1, color_name: str = "TARS") -> None:
    """Post-procesa un .3mf para añadir:

    · `<basematerials>` con el color (para que cualquier visor 3MF lo muestre).
    · `pid`/`pindex` en los `<object>` que tienen malla real → Bambu Studio lo
      reconoce como color del objeto.
    · `Metadata/model_settings.config` con el slot de filamento pre-asignado
      (extensión propietaria de Bambu/Orca Studio).

    Así, al abrir el .3mf en Bambu Studio, cada pieza ya trae su filamento AMS
    asignado (slot 1..4) y no hay que tocar nada.
    """
    if not path.exists():
        return
    r, g, b, a = rgba
    hex_color = "#{:02X}{:02X}{:02X}{:02X}".format(
        int(round(r * 255)), int(round(g * 255)),
        int(round(b * 255)), int(round(a * 255)),
    )

    # --- Leer zip completo en memoria ---
    with zipfile.ZipFile(path, "r") as zin:
        members = {name: zin.read(name) for name in zin.namelist()}

    model_key = "3D/3dmodel.model"
    if model_key not in members:
        return
    xml = members[model_key].decode("utf-8")

    # --- (a) inyectar <basematerials> al principio de <resources> ---
    mat_id = 1000   # id alto para no chocar con los existentes
    basemat_block = (
        f'<basematerials id="{mat_id}">'
        f'<base name="{color_name}" displaycolor="{hex_color}"/>'
        f'</basematerials>'
    )
    if "<basematerials" not in xml:
        xml = xml.replace("<resources>", f"<resources>{basemat_block}", 1)

    # --- (b) añadir pid/pindex a los <object type="model"> con <mesh> ---
    #     (sólo los que contienen malla real, no los de <components>)
    def _add_pid(match: re.Match) -> str:
        tag = match.group(0)
        if 'type="model"' not in tag:
            return tag
        if ' pid=' in tag:
            return tag
        # Sólo añadir si la siguiente aparición tras este tag es <mesh> (dentro
        # del mismo objeto); heurística por la ID — más fiable añadir a todos
        # y que los componentes lo ignoren.
        return tag[:-1] + f' pid="{mat_id}" pindex="0">'

    xml = re.sub(r"<object\s[^>]*>", _add_pid, xml)

    members[model_key] = xml.encode("utf-8")

    # --- (c) Metadata/model_settings.config (Bambu/Orca Studio) ---
    # Recorremos objetos y asignamos el mismo filamento a todos los que hay en
    # este fichero (cada 3MF aquí representa UNA sola pieza imprimible).
    obj_ids = re.findall(r'<object\s[^>]*id="(\d+)"[^>]*type="model"', xml)
    cfg_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<config>',
    ]
    for oid in obj_ids:
        cfg_lines.append(f'  <object id="{oid}">')
        cfg_lines.append(f'    <metadata key="extruder" value="{filament_slot}"/>')
        cfg_lines.append(f'    <metadata key="name" value="{color_name}"/>')
        cfg_lines.append('  </object>')
    cfg_lines.append('</config>')
    members["Metadata/model_settings.config"] = "\n".join(cfg_lines).encode("utf-8")

    # --- (d) asegurarnos de que [Content_Types].xml incluye el tipo config ---
    ct_key = "[Content_Types].xml"
    if ct_key in members:
        ct = members[ct_key].decode("utf-8")
        if 'Extension="config"' not in ct:
            ct = ct.replace(
                "</Types>",
                '<Default Extension="config" ContentType="application/vnd.bambulab-config+xml"/></Types>',
                1,
            )
            members[ct_key] = ct.encode("utf-8")

    # --- Reescribir zip ---
    tmp = path.with_suffix(".3mf.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in members.items():
            zout.writestr(name, data)
    shutil.move(str(tmp), str(path))


def _inject_3mf_multicolor(path: Path) -> None:
    """Versión multi-objeto para el 3MF de preview. Lee el ``partnumber`` de
    cada ``<object>`` y le aplica color + slot según ``COLORS`` / ``FILAMENT_SLOT``.
    """
    if not path.exists():
        return
    with zipfile.ZipFile(path, "r") as zin:
        members = {name: zin.read(name) for name in zin.namelist()}
    model_key = "3D/3dmodel.model"
    if model_key not in members:
        return
    xml = members[model_key].decode("utf-8")

    # 1) Generar un <basematerials> con un <base> por pieza única
    base_entries = []  # (mat_pindex, rgba, color_name)
    name_to_pindex: dict[str, int] = {}
    for pindex, (cname, rgba) in enumerate(COLORS.items()):
        base_entries.append((pindex, rgba, cname))
        name_to_pindex[cname] = pindex

    mat_id = 1000
    bases_xml = []
    for _, rgba, cname in base_entries:
        r, g, b, a = rgba
        hx = "#{:02X}{:02X}{:02X}{:02X}".format(
            int(round(r * 255)), int(round(g * 255)),
            int(round(b * 255)), int(round(a * 255)),
        )
        bases_xml.append(f'<base name="{cname}" displaycolor="{hx}"/>')
    basemat_block = f'<basematerials id="{mat_id}">{"".join(bases_xml)}</basematerials>'
    if "<basematerials" not in xml:
        xml = xml.replace("<resources>", f"<resources>{basemat_block}", 1)

    # 2) A cada <object type="model" partnumber="NN"...> añadirle pid/pindex
    def _repl(match: re.Match) -> str:
        tag = match.group(0)
        if 'type="model"' not in tag:
            return tag
        if ' pid=' in tag:
            return tag
        m = re.search(r'partnumber="([^"]+)"', tag)
        if not m:
            return tag
        base = m.group(1)
        for suf in ("_A_inferior", "_B_superior", "_proxy"):
            if base.endswith(suf):
                base = base[: -len(suf)]
                break
        if base not in name_to_pindex:
            return tag
        pindex = name_to_pindex[base]
        return tag[:-1] + f' pid="{mat_id}" pindex="{pindex}">'

    xml = re.sub(r"<object\s[^>]*>", _repl, xml)

    # 3) Config Bambu con filament slot por objeto
    obj_tag_re = re.compile(r'<object\s[^>]*>')
    cfg_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<config>']
    for m in obj_tag_re.finditer(xml):
        tag = m.group(0)
        if 'type="model"' not in tag:
            continue
        oid_m = re.search(r'id="(\d+)"', tag)
        pn_m = re.search(r'partnumber="([^"]+)"', tag)
        if not oid_m:
            continue
        oid = oid_m.group(1)
        base = pn_m.group(1) if pn_m else ""
        for suf in ("_A_inferior", "_B_superior", "_proxy"):
            if base.endswith(suf):
                base = base[: -len(suf)]
                break
        slot = FILAMENT_SLOT.get(base, 1)
        cfg_lines.append(f'  <object id="{oid}">')
        cfg_lines.append(f'    <metadata key="extruder" value="{slot}"/>')
        cfg_lines.append(f'    <metadata key="name" value="{base}"/>')
        cfg_lines.append('  </object>')
    cfg_lines.append('</config>')
    members["Metadata/model_settings.config"] = "\n".join(cfg_lines).encode("utf-8")

    ct_key = "[Content_Types].xml"
    if ct_key in members:
        ct = members[ct_key].decode("utf-8")
        if 'Extension="config"' not in ct:
            ct = ct.replace(
                "</Types>",
                '<Default Extension="config" ContentType="application/vnd.bambulab-config+xml"/></Types>',
                1,
            )
            members[ct_key] = ct.encode("utf-8")

    members[model_key] = xml.encode("utf-8")
    tmp = path.with_suffix(".3mf.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in members.items():
            zout.writestr(name, data)
    shutil.move(str(tmp), str(path))


def export_all(parts: dict[str, Part]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Piezas que sobrepasan la altura de impresión (351 > 256 en la X2D).
    # Se parten horizontalmente en 2 trozos con pines de alineación + M3.
    splittable = {"bloque_central", "brazo_izquierdo", "brazo_derecho", "tapa_trasera"}

    printable: dict[str, Part] = {}
    for name, part in parts.items():
        if SPLIT_ENABLED and name in splittable and HEIGHT > PRINT_MAX_Z:
            # Posiciones de dowels y tornillos según la pieza
            if name == "bloque_central":
                dowels = [
                    (-WIDTH_CENTRAL / 2 + WALL, -DEPTH / 2 + WALL),
                    (+WIDTH_CENTRAL / 2 - WALL, -DEPTH / 2 + WALL),
                    (-WIDTH_CENTRAL / 2 + WALL, +DEPTH / 2 - WALL),
                    (+WIDTH_CENTRAL / 2 - WALL, +DEPTH / 2 - WALL),
                ]
                screws = [(-WIDTH_CENTRAL / 2 + WALL + 3, 0), (+WIDTH_CENTRAL / 2 - WALL - 3, 0)]
                w, d = WIDTH_CENTRAL, DEPTH
            elif name in ("brazo_izquierdo", "brazo_derecho"):
                dowels = [
                    (-WIDTH_ARM / 2 + WALL, -DEPTH / 2 + WALL),
                    (+WIDTH_ARM / 2 - WALL, -DEPTH / 2 + WALL),
                    (-WIDTH_ARM / 2 + WALL, +DEPTH / 2 - WALL),
                    (+WIDTH_ARM / 2 - WALL, +DEPTH / 2 - WALL),
                ]
                screws = [(0, 0)]
                w, d = WIDTH_ARM, DEPTH
            else:  # tapa_trasera (plana 3mm)
                dowels = [
                    (-WIDTH_CENTRAL / 2 + 6, 0),
                    (+WIDTH_CENTRAL / 2 - 6, 0),
                ]
                screws = []
                w, d = WIDTH_CENTRAL, REAR_LID_T

            bot, top = split_piece(part, SPLIT_Z, w, d, dowels, screws)
            # Heredar color de la pieza original
            col = getattr(part, "color", None)
            if col is not None:
                try:
                    bot.color = col
                    top.color = col
                except Exception:
                    pass
            printable[f"{name}_A_inferior"] = bot
            printable[f"{name}_B_superior"] = top
        else:
            printable[name] = part

    # Fusionar sólidos sueltos en uno sólo por pieza. Sin esto, piezas con
    # cunas/clips interiores que no tocan las paredes exteriores quedan como
    # varios sólidos desconectados dentro del 3MF, y Bambu Studio los detecta
    # como "multi-part object at multiple heights".
    def _unify_solids(p: Part) -> Part:
        try:
            solids = p.solids()
            if len(solids) <= 1:
                return p
            s0 = solids[0]
            for s in solids[1:]:
                s0 = s0.fuse(s)
            unified = Part(s0.wrapped)
            if getattr(p, "color", None) is not None:
                try:
                    unified.color = p.color
                except Exception:
                    pass
            return unified
        except Exception:
            return p

    printable = {n: _unify_solids(p) for n, p in printable.items()}

    # STL por pieza lista para imprimir
    for name, part in printable.items():
        stl_path = OUT_DIR / f"{name}.stl"
        export_stl(part, str(stl_path))
        print(f"  → {stl_path.relative_to(OUT_DIR.parent)}")

    # 3MF por pieza lista para imprimir (Bambu Studio los importa individualmente
    # y los coloca en la cama; cada uno ya está orientado y dentro de 256³).
    ok, ko = 0, 0
    for name, part in printable.items():
        mf = OUT_DIR / f"{name}.3mf"
        try:
            mesher = Mesher()
            mesher.add_shape(part, part_number=name)
            mesher.write(str(mf))
            # Consolidar en un único objeto para evitar el aviso
            # "multi-part object detected" en Bambu Studio.
            _consolidate_3mf_single_object(mf)
            # Determinar color y slot a partir del nombre base (sin _A_inferior/_B_superior)
            base = name
            for suf in ("_A_inferior", "_B_superior"):
                if base.endswith(suf):
                    base = base[: -len(suf)]
                    break
            rgba = COLORS.get(base, (0.8, 0.8, 0.8, 1.0))
            slot = FILAMENT_SLOT.get(base, 1)
            _inject_3mf_color(mf, rgba, filament_slot=slot, color_name=base)
            ok += 1
        except Exception as e:
            ko += 1
            print(f"  ! {name}.3mf saltado ({type(e).__name__}: {e}); usa el STL")
    print(f"  → {ok} ficheros .3mf generados ({ko} omitidos — STL disponibles)")

    # -------------------------------------------------------------------
    # STL y 3MF de PREVIEW — todas las piezas ensambladas en su sitio.
    # Sólo para ver cómo queda el robot entero (NO uos sar para imprimir).
    # -------------------------------------------------------------------
    # Separación visual (gap de aire entre brazos y central, como en la foto real)
    PREVIEW_GAP = 3.0
    x_izq = -(WIDTH_CENTRAL / 2 + PREVIEW_GAP + WIDTH_ARM / 2)
    x_der = +(WIDTH_CENTRAL / 2 + PREVIEW_GAP + WIDTH_ARM / 2)
    placements = [
        ("bloque_central",   (0, 0, 0)),
        ("tapa_trasera",     (0, DEPTH / 2 - REAR_LID_T / 2, (HEIGHT - 4.0) / 2)),
        ("brazo_izquierdo",  (x_izq, 0, 0)),
        ("brazo_derecho",    (x_der, 0, 0)),
        ("tapa_superior",    (0, 0, HEIGHT - 4.0)),
        ("soporte_servos",   (0, 0, 0)),
    ]

    def _moved(shape, pos):
        loc = Location(pos)
        if hasattr(shape, "moved"):
            return shape.moved(loc)
        try:
            return Compound(children=[s.moved(loc) for s in shape])
        except Exception:
            return shape

    preview_parts = [_moved(parts[n], pos) for n, pos in placements]
    preview = Compound(label="TARS_preview", children=preview_parts)

    preview_stl = OUT_DIR / "PREVIEW_tars_robot.stl"
    try:
        export_stl(preview, str(preview_stl))
        print(f"  → {preview_stl.relative_to(OUT_DIR.parent)}  (VISTA COMPLETA ensamblada)")
    except Exception as e:
        print(f"  ! preview STL saltado: {e}")

    # 3MF de preview con colores — cada pieza como objeto separado.
    # Tolerante a fallos: si el bloque central falla la malla, lo sustituyo
    # por una caja proxy para que el resto mantenga sus colores.
    preview_3mf = OUT_DIR / "PREVIEW_tars_robot.3mf"
    mesher = Mesher()
    ok_p, ko_p = 0, 0
    for name, pos in placements:
        shape = _moved(parts[name], pos)
        try:
            mesher.add_shape(shape, part_number=name)
            ok_p += 1
        except Exception:
            # fallback: caja proxy del mismo color, tamaño aproximado
            ko_p += 1
            try:
                if name == "bloque_central":
                    proxy = Box(WIDTH_CENTRAL, DEPTH, HEIGHT,
                                align=(Align.CENTER, Align.CENTER, Align.MIN))
                elif name.startswith("brazo"):
                    proxy = Box(WIDTH_ARM, DEPTH, HEIGHT,
                                align=(Align.CENTER, Align.CENTER, Align.MIN))
                else:
                    continue
                try:
                    proxy.color = parts[name].color
                except Exception:
                    pass
                mesher.add_shape(_moved(proxy, pos), part_number=name + "_proxy")
            except Exception as e2:
                print(f"  ! preview {name} omitido: {type(e2).__name__}")
    try:
        mesher.write(str(preview_3mf))
        _inject_3mf_multicolor(preview_3mf)
        print(f"  → {preview_3mf.relative_to(OUT_DIR.parent)}  (VISTA con colores — {ok_p} ok, {ko_p} proxy)")
    except Exception as e:
        print(f"  ! preview 3MF saltado: {type(e).__name__}: {e}")


def summary() -> None:
    print("─" * 60)
    print("TARS — Chasis paramétrico")
    print("─" * 60)
    print(f"  Alto × Ancho × Fondo : {HEIGHT:.0f} × {WIDTH_TOTAL:.0f} × {DEPTH:.0f} mm")
    print(f"  Bloque central        : {WIDTH_CENTRAL:.0f} × {DEPTH:.0f} × {HEIGHT-4:.0f} mm")
    print(f"  Tapa trasera          : {WIDTH_CENTRAL:.0f} × {REAR_LID_T:.0f} × {HEIGHT-4:.0f} mm  (snap-fit, sin tornillos)")
    print(f"  Brazo lateral (×2)    : {WIDTH_ARM:.0f} × {DEPTH:.0f} × {HEIGHT:.0f} mm")
    print(f"  Tapa superior         : {WIDTH_CENTRAL:.0f} × {DEPTH:.0f} × 4 mm  (USB-C)")
    print(f"  Unidad modular        : {UNIT:.0f} mm ({HEIGHT//UNIT:.0f}u × {DEPTH//UNIT:.0f}u × 1u)")
    print(f"  Pared exterior        : {WALL} mm")
    print(f"  Unión brazo↔central   : servo (z={SERVO_AXIS_Z}), sin pivote superior")
    if SPLIT_ENABLED and HEIGHT > PRINT_MAX_Z:
        print(f"  Partido para X2D      : SÍ, corte a z={SPLIT_Z} mm (volumen 256³)")
        print(f"                          4× dowel ø{SPLIT_DOWEL_D} + 2× M3 por unión")
    print("─" * 60)


if __name__ == "__main__":
    summary()
    parts = build_all()
    export_all(parts)

    # Visualización en VS Code (requiere: pip install ocp-vscode
    # + extensión "OCP CAD Viewer"). Si no está, se omite en silencio.
    try:
        from ocp_vscode import show, set_port
        set_port(3939)

        def _mv(shape, pos):
            loc = Location(pos)
            if hasattr(shape, "moved"):
                return shape.moved(loc)
            # ShapeList / Compound → mover cada sólido
            try:
                return Compound(children=[s.moved(loc) for s in shape])
            except Exception:
                return shape

        x_izq = -(WIDTH_CENTRAL / 2 + ARM_GAP + WIDTH_ARM / 2)
        x_der = +(WIDTH_CENTRAL / 2 + ARM_GAP + WIDTH_ARM / 2)

        # Cambia esto para ver sólo una pieza en el OCP viewer.
        # Opciones: None (todo), "bloque_central", "tapa_trasera",
        #           "brazo_izquierdo", "brazo_derecho", "tapa_superior"
        SHOW_ONLY = None

        _all = [
            ("bloque_central",   parts["bloque_central"],   (0, 0, 0),                                 "central",      "#888"),
            ("tapa_trasera",     parts["tapa_trasera"],     (0, DEPTH / 2 - REAR_LID_T / 2, (HEIGHT - 4.0) / 2),  "tapa_trasera", "#555"),
            ("brazo_izquierdo",  parts["brazo_izquierdo"],  (x_izq, 0, 0),                             "brazo_izq",    "#c44"),
            ("brazo_derecho",    parts["brazo_derecho"],    (x_der, 0, 0),                             "brazo_der",    "#c44"),
            ("tapa_superior",    parts["tapa_superior"],    (0, 0, HEIGHT - 4.0),                      "tapa_sup",     "#444"),
        ]
        if SHOW_ONLY:
            _all = [e for e in _all if e[0] == SHOW_ONLY]
            # Aislada al origen para verla centrada
            _all = [(k, parts[k], (0, 0, 0), n, c) for (k, _p, _pos, n, c) in _all]

        show(
            *[_mv(p, pos) for (_k, p, pos, _n, _c) in _all],
            names=[n for (*_x, n, _c) in _all],
            colors=[c for (*_x, _n, c) in _all],
        )
        print("\n🖼  Modelo enviado al OCP CAD Viewer.")
    except ImportError:
        print("\nℹ  Para visualizar: pip install ocp-vscode + extensión 'OCP CAD Viewer'.")

    print("\n✅ Listo. Abre los .3mf en Bambu Studio para imprimir.")

