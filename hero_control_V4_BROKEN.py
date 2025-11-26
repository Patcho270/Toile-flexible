# Contrôle Hero avec Debug Method Tracking
# Configuré sur le CHOP 'hero_control'

def onValueChange(channel, sampleIndex, val, prev):
    """
    Appelé quand n'importe quel channel du CHOP change de valeur
    """

    # Récupérer le CHOP hero_control
    hero_chop = op('hero_control')

    if not hero_chop or hero_chop.numChans < 2:
        return

    # Lire les valeurs x et y
    x = hero_chop[0].eval()
    y = hero_chop[1].eval()

    # DEBUG: Lire la méthode de détection depuis le Null CHOP detection_methode
    method = 0  # Par défaut bump
    hand_active = True  # Par défaut main active

    detection_methode = op('detection_methode')
    if detection_methode:
        try:
            method = int(detection_methode['method'][0])  # 0 = bump, 1 = mediapipe

            # Écrire dans le Constant CHOP de debug
            debug_constant = op('constant_debug_method_tracking')
            if debug_constant:
                # Channel 0 = la valeur de method (0 ou 1)
                debug_constant.par.value0 = method

            # Si méthode = 1 (MediaPipe), vérifier si la main est active
            if method == 1:
                select_mediapipe = op('select_all_mediapipe')
                if select_mediapipe:
                    try:
                        hand_active_value = select_mediapipe['h1:hand_active'][0]
                        hand_active = (hand_active_value > 0)
                    except:
                        hand_active = False
        except:
            pass

    # Récupérer le Web Render TOP
    web = op('webrender1')
    if not web:
        return

    # Si MediaPipe ET main inactive, activer la rétractation
    if method == 1 and not hand_active:
        js = "if(window.startRetraction) window.startRetraction({}, {});".format(x, y)
        try:
            web.executeJavaScript(js)
        except:
            pass
        return  # Ne pas continuer, rétractation activée

    # Vérifier si le hero est aux bords (désactiver les connexions)
    # Bords: x = 0 ou 1080, y = 0 ou 1080
    at_edge = (x <= 0 or x >= 1080 or y <= 0 or y >= 1080)

    # Si aux bords, désactiver les connexions (CONNECT_DISTANCE = 0)
    # Sinon, réactiver (CONNECT_DISTANCE = 480)
    if at_edge:
        js_distance = "CONNECT_DISTANCE = 0;"
    else:
        js_distance = "CONNECT_DISTANCE = 480;"

    # Construire et exécuter le JavaScript
    js = js_distance + "if(window.setHeroPosition) window.setHeroPosition({}, {});".format(x, y)

    try:
        web.executeJavaScript(js)
    except Exception as e:
        pass


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
# 3. Rétractation intelligente: Si MediaPipe + main inactive → startRetraction(lastX, lastY)
#    → HTML place hero à (-5000, -5000) pour distance, mais utilise (lastX, lastY) pour direction
#    → Les gouttes se rétractent depuis la bonne direction
# 4. Détection bords: Si x/y = 0 ou 1080, désactive les connexions
# 5. Contrôle HTML: Envoie position au hero ball via JavaScript
#
# =============================================================================
