# =============================================================================
# BRIDGE MIDI CONTROLLER - Contrôle MIDI basé sur les bridges actifs
# =============================================================================
# À copier dans un Execute DAT (famille DAT)
# Lit proximity_dat pour détecter les bridges actifs
# Joue une note MIDI pour chaque boule avec bridge actif
# La note est basée sur la position XY de la boule
# =============================================================================

import math

# --- Configuration MIDI ---
# Chaque boule (0-4) a son propre opérateur MIDI Out CHOP
MIDI_OPS = {
    0: '/project1/Tda_MIDI_1',
    1: '/project1/Tda_MIDI_2',
    2: '/project1/Tda_MIDI_3',
    3: '/project1/Tda_MIDI_4',
    4: '/project1/Tda_MIDI_5'
}

# Chaque boule (0-4) a son propre paramètre Ableton pour contrôler les effets
ABLETON_PARAMS = {
    0: '/project1/abletonParameter_1',
    1: '/project1/abletonParameter_2',
    2: '/project1/abletonParameter_3',
    3: '/project1/abletonParameter_4',
    4: '/project1/abletonParameter_5'
}

# Distance maximale de bridge (doit correspondre à proximity_calculator.py)
CONNECT_DISTANCE = 480

# Gamme pentatonique majeure : C, D, E, G, A
PENTATONIC = [0, 2, 4, 7, 9]

# Plage de notes MIDI
BASE_NOTE = 36   # C3
TOP_NOTE = 96    # C8

# Velocity neutre (ni trop fort, ni trop faible)
DEFAULT_VELOCITY = 80

# --- État global ---
# Dictionnaire pour tracker les notes actives par ball_id
# Format: {ball_id: note_midi}
active_notes = {}


def send_midi(ball_id, note, velocity):
    """
    Envoie une note MIDI à l'opérateur MIDI correspondant à la boule.

    Args:
        ball_id: ID de la boule (0-4)
        note: Note MIDI (0-127)
        velocity: Vélocité (0-127), 0 = Note OFF
    """
    # Récupérer le bon opérateur MIDI pour cette boule
    if ball_id not in MIDI_OPS:
        return

    midi = op(MIDI_OPS[ball_id])
    if midi is None:
        return

    note_int = int(max(0, min(127, note)))
    vel_int = int(max(0, min(127, velocity)))
    midi.SendMIDI('note', note_int, vel_int)


def update_ableton_parameter(ball_id, distance):
    """
    Met à jour le paramètre Ableton basé sur la distance hero-boule.

    Logique:
        - Distance proche (0) → Valeur 0.0
        - Distance loin (480) → Valeur 0.5
        - Pas de bridge → Valeur 0.0

    Args:
        ball_id: ID de la boule (0-4)
        distance: Distance en pixels (0-480)
    """
    if ball_id not in ABLETON_PARAMS:
        return

    param = op(ABLETON_PARAMS[ball_id])
    if param is None:
        return

    # Mapper distance (0-480) sur valeur (0.0-0.5)
    # Distance 0 = très proche = valeur 0
    # Distance 480 = très loin (limite bridge) = valeur 0.5
    if distance > 0:
        normalized_value = (distance / CONNECT_DISTANCE) * 0.5
        normalized_value = max(0.0, min(0.5, normalized_value))
    else:
        normalized_value = 0.0

    # Modifier le paramètre "Valuesend" du CHOP
    try:
        param.par.Valuesend = normalized_value
    except:
        pass


def quantize_to_uniform_pentatonic(val_x, val_y, max_x, max_y):
    """
    Mappe dynamiquement la position XY d'une boule sur une note MIDI.

    Args:
        val_x: Position X de la boule (0 à max_x)
        val_y: Position Y de la boule (0 à max_y)
        max_x: Résolution largeur (ex: 1920)
        max_y: Résolution hauteur (ex: 1080)

    Returns:
        note: Note MIDI (36-96)
    """

    # Normaliser les valeurs en 0-127 pour compatibilité
    if max_x > 0:
        normalized_x = (val_x / max_x) * 127
    else:
        normalized_x = 0

    if max_y > 0:
        normalized_y = (val_y / max_y) * 127
    else:
        normalized_y = 0

    # Clamp
    normalized_x = max(0, min(127, normalized_x))
    normalized_y = max(0, min(127, normalized_y))

    # --- 1️⃣ Sélection de la note (via X)
    note_range = TOP_NOTE - BASE_NOTE
    f = normalized_x / 127.0
    raw_note = BASE_NOTE + f * note_range
    semitone = int(round(raw_note)) - BASE_NOTE
    degree_in_octave = semitone % 12
    closest = min(PENTATONIC, key=lambda n: abs(n - degree_in_octave))
    note_in_scale = BASE_NOTE + closest

    # --- 2️⃣ Sélection de l'octave (via Y)
    octave_count = 3  # 3 octaves disponibles
    octave = int((normalized_y / 127.0) * octave_count)  # 0-2
    note = note_in_scale + 12 * octave

    # Clamp final
    note = max(BASE_NOTE, min(TOP_NOTE, note))
    return note


def onFrameStart(frame):
    """
    Appelé à chaque frame.
    Lit proximity_dat et joue les notes MIDI pour chaque bridge actif.
    """
    global active_notes

    # Récupérer proximity_dat
    proximity_dat = op('proximity_dat')
    if not proximity_dat or proximity_dat.numRows < 2:
        return

    # Récupérer la résolution dynamique
    resolution_chop = op('webrender_resolution')
    if not resolution_chop or resolution_chop.numChans < 2:
        return

    try:
        # Lire résolution (resolutionw, resolutionh)
        res_w = resolution_chop['resolutionw'][0]
        res_h = resolution_chop['resolutionh'][0]
    except:
        return

    # Set pour tracker quelles boules ont un bridge actif ce frame
    current_active_balls = set()

    # Parcourir proximity_dat (skip header row 0)
    for row in range(1, proximity_dat.numRows):
        try:
            ball_id = int(proximity_dat[row, 0].val)
            distance = float(proximity_dat[row, 1].val)
            bridge_active = int(proximity_dat[row, 2].val)
            ball_x = float(proximity_dat[row, 3].val)
            ball_y = float(proximity_dat[row, 4].val)

            if bridge_active == 1:
                # Bridge actif pour cette boule
                current_active_balls.add(ball_id)

                # Mettre à jour le paramètre Ableton basé sur la distance
                update_ableton_parameter(ball_id, distance)

                # Calculer la note basée sur la position de la boule
                new_note = quantize_to_uniform_pentatonic(ball_x, ball_y, res_w, res_h)

                # Vérifier si cette boule joue déjà une note
                if ball_id in active_notes:
                    old_note = active_notes[ball_id]

                    # Si la note a changé, stop l'ancienne et joue la nouvelle
                    if old_note != new_note:
                        send_midi(ball_id, old_note, 0)
                        send_midi(ball_id, new_note, DEFAULT_VELOCITY)
                        active_notes[ball_id] = new_note
                else:
                    # Nouvelle boule avec bridge, jouer la note
                    send_midi(ball_id, new_note, DEFAULT_VELOCITY)
                    active_notes[ball_id] = new_note

        except Exception as e:
            continue

    # --- Note OFF pour les boules qui n'ont plus de bridge ---
    balls_to_stop = []
    for ball_id, note in active_notes.items():
        if ball_id not in current_active_balls:
            # Cette boule n'a plus de bridge actif
            send_midi(ball_id, note, 0)
            update_ableton_parameter(ball_id, 0)  # Remettre le paramètre à 0
            balls_to_stop.append(ball_id)

    # Nettoyer le dictionnaire
    for ball_id in balls_to_stop:
        del active_notes[ball_id]


def onFrameEnd(frame):
    pass


# =============================================================================
# SETUP TOUCHDESIGNER
# =============================================================================
#
# 1. Créez un Execute DAT
#    - Palette → DAT → Execute
#    - Nommez-le : bridge_midi_controller
#
# 2. Configurez-le :
#    - Parameters → Execute
#    - Frame Start: ON ✓
#
# 3. Copiez ce code dans le Execute DAT
#
# 4. Vérifiez que vous avez :
#    - proximity_dat (Table DAT avec colonnes: ball_id, distance, bridge_active, ball_x, ball_y, angle)
#    - webrender_resolution (Constant CHOP avec channels: resolutionw, resolutionh)
#
#    MIDI Out CHOPs (5 opérateurs) :
#    - /project1/Tda_MIDI_1 (pour boule 0)
#    - /project1/Tda_MIDI_2 (pour boule 1)
#    - /project1/Tda_MIDI_3 (pour boule 2)
#    - /project1/Tda_MIDI_4 (pour boule 3)
#    - /project1/Tda_MIDI_5 (pour boule 4)
#
#    Paramètres Ableton CHOPs (5 opérateurs avec paramètre Valuesend) :
#    - /project1/abletonParameter_1 (pour boule 0) - paramètre "Valuesend" modifié
#    - /project1/abletonParameter_2 (pour boule 1) - paramètre "Valuesend" modifié
#    - /project1/abletonParameter_3 (pour boule 2) - paramètre "Valuesend" modifié
#    - /project1/abletonParameter_4 (pour boule 3) - paramètre "Valuesend" modifié
#    - /project1/abletonParameter_5 (pour boule 4) - paramètre "Valuesend" modifié
#
# 5. Jouez !
#    - Quand le hero s'approche d'une boule → note MIDI joue
#    - Position X de la boule → Note (gauche = grave, droite = aigu)
#    - Position Y de la boule → Octave (haut = aigu, bas = grave)
#    - Plusieurs boules = plusieurs notes simultanées (polyphonie)
#
#    Contrôle de distance dynamique :
#    - Très proche (0 pixels) → Paramètre = 0.0
#    - Très loin (480 pixels, limite bridge) → Paramètre = 0.5
#    - Bridge inactif → Paramètre = 0.0
#
# =============================================================================
