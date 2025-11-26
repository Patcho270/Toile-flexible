# =============================================================================
# PROXIMITY CALCULATOR - Calcul distances Hero ↔ Boules
# =============================================================================
# À copier dans un Execute DAT (famille DAT)
# Calcule la distance entre le hero et chaque boule stationnaire
# Output dans un DAT Table nommé 'proximity_dat'
#
# LOGIQUE :
# - Si distance <= 320 pixels (CONNECT_DISTANCE) → bridge actif → affiche distance
# - Si distance > 320 pixels → pas de bridge → affiche 0
# =============================================================================

import math

# Distance maximale pour créer un bridge (même valeur que dans metaball.html)
CONNECT_DISTANCE = 480  # 1.5x plus loin (était 320)

def onFrameStart(frame):
    """
    Calculé à chaque frame
    """

    # Récupérer le CHOP hero_control
    hero_chop = op('hero_control')
    if not hero_chop or hero_chop.numChans < 2:
        return

    # Récupérer le DAT Table des positions des boules
    balls_table = op('balls_positions_table')
    if not balls_table:
        return

    # Récupérer le DAT de sortie
    proximity_dat = op('proximity_dat')
    if not proximity_dat:
        return

    # Lire position du hero
    hero_x = hero_chop[0].eval()
    hero_y = hero_chop[1].eval()

    # Configurer le DAT de sortie (header + 5 lignes)
    if proximity_dat.numRows < 6:
        proximity_dat.clear()
        proximity_dat.appendRow(['ball_id', 'distance', 'bridge_active', 'ball_x', 'ball_y', 'angle'])

    # Calculer distances pour chaque boule
    distances = []

    for row in range(1, min(balls_table.numRows, 6)):  # 5 boules (rows 1-5)
        try:
            ball_x = float(balls_table[row, 1].val)
            ball_y = float(balls_table[row, 2].val)

            # Calcul de la distance euclidienne
            dx = ball_x - hero_x
            dy = ball_y - hero_y
            distance = math.sqrt(dx * dx + dy * dy)

            ball_id = int(balls_table[row, 0].val)

            # Calcul de l'angle (en degrés 0-360) entre hero et boule
            # atan2(dy, dx) donne l'angle en radians, on le convertit en degrés
            if distance <= CONNECT_DISTANCE:
                angle_rad = math.atan2(dy, dx)
                angle_deg = math.degrees(angle_rad)
                # Normaliser de -180/180 vers 0/360
                if angle_deg < 0:
                    angle_deg += 360
                angle = angle_deg
            else:
                angle = 0  # Pas d'angle si pas de bridge

            # Détection de bridge : si distance <= 320, bridge actif
            if distance <= CONNECT_DISTANCE:
                bridge_active = 1
                output_distance = distance
            else:
                bridge_active = 0
                output_distance = 0

            distances.append([ball_id, output_distance, bridge_active, ball_x, ball_y, angle])

        except Exception as e:
            distances.append([row - 1, 0, 0, 0, 0, 0])

    # Remplir le DAT de sortie
    proximity_dat.clear()
    proximity_dat.appendRow(['ball_id', 'distance', 'bridge_active', 'ball_x', 'ball_y', 'angle'])

    for ball_id, dist, bridge, bx, by, ang in distances:
        proximity_dat.appendRow([
            str(ball_id), 
            '{:.2f}'.format(dist), 
            str(bridge),
            '{:.2f}'.format(bx),
            '{:.2f}'.format(by),
            '{:.1f}'.format(ang)
        ])


def onFrameEnd(frame):
    pass


# =============================================================================
# ALTERNATIVE : Version optimisée avec mise à jour sélective
# =============================================================================

def onFrameStart_OPTIMIZED(frame):
    """
    Version qui ne met à jour que si les positions ont changé
    """

    hero_chop = op('hero_control')
    balls_table = op('balls_positions_table')
    proximity_dat = op('proximity_dat')

    if not all([hero_chop, balls_table, proximity_dat]):
        return

    if hero_chop.numChans < 2:
        return

    hero_x = hero_chop[0].eval()
    hero_y = hero_chop[1].eval()

    # Initialiser le header si nécessaire
    if proximity_dat.numRows == 0:
        proximity_dat.appendRow(['ball_id', 'distance', 'bridge_active', 'ball_x', 'ball_y', 'angle'])

    # Calculer et mettre à jour
    for i, row in enumerate(range(1, min(balls_table.numRows, 6)), start=1):
        try:
            ball_x = float(balls_table[row, 1].val)
            ball_y = float(balls_table[row, 2].val)

            dx = ball_x - hero_x
            dy = ball_y - hero_y
            distance = math.sqrt(dx * dx + dy * dy)

            ball_id = balls_table[row, 0].val

            # Calcul de l'angle (en degrés 0-360)
            if distance <= CONNECT_DISTANCE:
                angle_rad = math.atan2(dy, dx)
                angle_deg = math.degrees(angle_rad)
                if angle_deg < 0:
                    angle_deg += 360
                angle = angle_deg
                bridge_active = 1
            else:
                angle = 0
                bridge_active = 0

            # Créer la ligne si elle n'existe pas
            if proximity_dat.numRows <= i:
                proximity_dat.appendRow([
                    ball_id, 
                    '{:.2f}'.format(distance), 
                    str(bridge_active),
                    '{:.2f}'.format(ball_x),
                    '{:.2f}'.format(ball_y),
                    '{:.1f}'.format(angle)
                ])
            else:
                proximity_dat[i, 0] = ball_id
                proximity_dat[i, 1] = '{:.2f}'.format(distance)
                proximity_dat[i, 2] = str(bridge_active)
                proximity_dat[i, 3] = '{:.2f}'.format(ball_x)
                proximity_dat[i, 4] = '{:.2f}'.format(ball_y)
                proximity_dat[i, 5] = '{:.1f}'.format(angle)

        except Exception as e:
            pass
