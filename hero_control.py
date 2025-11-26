# Contrôle Hero avec Debug Method Tracking + FSM Hand Active
# Configuré sur le CHOP 'hero_control'

# Globals pour FSM hand_active
last_hand_active = 0
last_hero_x = 540
last_hero_y = 540

def onValueChange(channel, sampleIndex, val, prev):
    """
    Appelé quand n'importe quel channel du CHOP change de valeur
    """
    global last_hand_active, last_hero_x, last_hero_y

    # Récupérer le CHOP hero_control
    hero_chop = op('hero_control')
    if not hero_chop or hero_chop.numChans < 2:
        return

    # Lire les valeurs x et y
    x = float(hero_chop[0].eval())
    y = float(hero_chop[1].eval())

    # Sauvegarder la dernière position
    last_hero_x = x
    last_hero_y = y

    # Lire la méthode de détection (0 = bump, 1 = mediapipe)
    method = 0
    detection_methode = op('detection_methode')
    if detection_methode:
        try:
            method = int(detection_methode['method'][0])

            # Debug tracking
            debug_constant = op('constant_debug_method_tracking')
            if debug_constant:
                debug_constant.par.value0 = method
        except:
            pass

    # Détection des bords (désactiver connexions)
    at_edge = (x <= 0 or x >= 1080 or y <= 0 or y >= 1080)
    js_distance = "CONNECT_DISTANCE = 0;" if at_edge else "CONNECT_DISTANCE = 480;"

    # Récupérer le Web Render TOP
    web = op('webrender1')
    if not web:
        return

    # === FSM HAND ACTIVE (MediaPipe uniquement) ===

    # Mode bump (0) → Toujours envoyer la position
    if method == 0:
        hand_js = "if(window.setHandActive) window.setHandActive(true);"
        js = hand_js + js_distance + "if(window.setHeroPosition) window.setHeroPosition({}, {});".format(x, y)
        web.executeJavaScript(js)
        last_hand_active = 0  # Reset FSM
        return

    # Mode MediaPipe (1) → FSM hand_active
    hand_active = 0
    select_mediapipe = op('select_all_mediapipe')
    if select_mediapipe:
        try:
            hand_active = int(select_mediapipe['h1:hand_active'][0])
        except:
            hand_active = 0

    # Main présente (hand_active > 0)
    if hand_active > 0:
        # Si on revient d'une disparition → réafficher le hero
        if last_hand_active == 0:
            web.executeJavaScript("if(window.showHero) window.showHero();")

        # Envoyer état main active + position normalement
        hand_js = "if(window.setHandActive) window.setHandActive(true);"
        js = hand_js + js_distance + "if(window.setHeroPosition) window.setHeroPosition({}, {});".format(x, y)
        web.executeJavaScript(js)

    # Main absente (hand_active == 0)
    else:
        # Désactiver état main + garder hero à dernière position
        hand_js = "if(window.setHandActive) window.setHandActive(false);"
        js = hand_js + js_distance + "if(window.setHeroPosition) window.setHeroPosition({}, {});".format(last_hero_x, last_hero_y)
        web.executeJavaScript(js)

    # Mettre à jour l'état
    last_hand_active = hand_active


def offToOn(channel, sampleIndex, val, prev):
    """Appelé quand un channel passe de 0 à non-zéro"""
    pass


def whileOn(channel, sampleIndex, val, prev):
    """Appelé chaque frame tant qu'un channel est non-zéro"""
    pass


def onToOff(channel, sampleIndex, val, prev):
    """Appelé quand un channel passe de non-zéro à 0"""
    pass


def whileOff(channel, sampleIndex, val, prev):
    """Appelé chaque frame tant qu'un channel est à 0"""
    pass


def afterCook(channel, sampleIndex, val, prev):
    """Appelé après que le CHOP ait cuisiné"""
    pass


# =============================================================================
# FONCTIONNALITÉS
# =============================================================================
#
# 1. Lit hero_control (X, Y) - reçoit bump detection OU mediapipe
# 2. DEBUG: Lit detection_methode['method'] et écrit dans constant_debug_method_tracking
# 3. FSM hand_active: Détecte quand la main MediaPipe disparaît/réapparaît
#    - Main disparaît → window.retractBridges(lastX, lastY) UNE FOIS
#    - Main réapparaît → window.showHero() + setHeroPosition(x, y)
# 4. Détection bords: Si x/y = 0 ou 1080, désactive les connexions
# 5. Contrôle HTML: Envoie position au hero ball via JavaScript
#
# =============================================================================
