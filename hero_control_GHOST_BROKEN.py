# Contrôle Hero avec Debug Method Tracking + Ghost Mode Retraction
# Configuré sur le CHOP 'hero_control'
# Ghost mode: anime le hero vers les boules quand main disparaît

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

    # Récupérer le parent pour accéder au storage
    parent_exec = parent()

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

    # Si MediaPipe ET main inactive, activer/animer ghost mode
    if method == 1 and not hand_active:
        ghost_active = parent_exec.fetch('ghostActive', False)

        if not ghost_active:
            # Premier frame: calculer cible
            # Premier frame de ghost mode: calculer la cible
            last_x = parent_exec.fetch('lastHeroX', 540.0)
            last_y = parent_exec.fetch('lastHeroY', 540.0)

            # Lire positions des boules depuis le CSV
            balls_table = op('balls_positions_table')
            if balls_table:
                total_weight = 0
                weighted_x = 0
                weighted_y = 0
                CONNECT_DISTANCE = 480

                for row in range(1, min(balls_table.numRows, 6)):  # 5 boules
                    try:
                        ball_x = float(balls_table[row, 1].val)
                        ball_y = float(balls_table[row, 2].val)

                        dx = last_x - ball_x
                        dy = last_y - ball_y
                        dist = (dx*dx + dy*dy) ** 0.5

                        if dist <= CONNECT_DISTANCE:
                            weight = 1 - (dist / CONNECT_DISTANCE)
                            total_weight += weight
                            weighted_x += ball_x * weight
                            weighted_y += ball_y * weight
                    except:
                        pass

                if total_weight > 0:
                    target_x = weighted_x / total_weight
                    target_y = weighted_y / total_weight
                else:
                    target_x = 540
                    target_y = 540

                parent_exec.store('ghostTargetX', target_x)
                parent_exec.store('ghostTargetY', target_y)
                parent_exec.store('ghostCurrentX', last_x)
                parent_exec.store('ghostCurrentY', last_y)
                parent_exec.store('ghostActive', True)
        else:
            # Animer chaque frame
            current_x = parent_exec.fetch('ghostCurrentX', 540.0)
            current_y = parent_exec.fetch('ghostCurrentY', 540.0)
            target_x = parent_exec.fetch('ghostTargetX', 540.0)
            target_y = parent_exec.fetch('ghostTargetY', 540.0)

            GHOST_SPEED = 0.08

            dx = target_x - current_x
            dy = target_y - current_y
            dist = (dx*dx + dy*dy) ** 0.5

            if dist > 5:
                new_x = current_x + dx * GHOST_SPEED
                new_y = current_y + dy * GHOST_SPEED

                parent_exec.store('ghostCurrentX', new_x)
                parent_exec.store('ghostCurrentY', new_y)

                web = op('webrender1')
                if web:
                    js = "if(window.setHeroPosition) window.setHeroPosition({}, {});".format(new_x, new_y)
                    try:
                        web.executeJavaScript(js)
                    except:
                        pass
            else:
                # Arrivé
                web = op('webrender1')
                if web:
                    js = "if(window.hideHero) window.hideHero();"
                    try:
                        web.executeJavaScript(js)
                    except:
                        pass
                parent_exec.store('ghostActive', False)

        return  # Ne pas continuer

    # Vérifier si le hero est aux bords (désactiver les connexions)
    # Bords: x = 0 ou 1080, y = 0 ou 1080
    at_edge = (x <= 0 or x >= 1080 or y <= 0 or y >= 1080)

    # Récupérer le Web Render TOP
    web = op('webrender1')

    if not web:
        return

    # Si aux bords, désactiver les connexions (CONNECT_DISTANCE = 0)
    # Sinon, réactiver (CONNECT_DISTANCE = 480)
    if at_edge:
        js_distance = "CONNECT_DISTANCE = 0;"
    else:
        js_distance = "CONNECT_DISTANCE = 480;"

    # Sauvegarder position pour ghost mode
    parent_exec.store('lastHeroX', x)
    parent_exec.store('lastHeroY', y)
    # Désactiver ghost mode (main est revenue)
    parent_exec.store('ghostActive', False)

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
    """Appelé chaque frame - utilisé pour animer le ghost mode"""
    parent_exec = parent()
    ghost_active = parent_exec.fetch('ghostActive', False)

    if ghost_active:
        print("Ghost mode active, animating...")  # DEBUG
        # Animer vers la cible
        current_x = parent_exec.fetch('ghostCurrentX', 540.0)
        current_y = parent_exec.fetch('ghostCurrentY', 540.0)
        target_x = parent_exec.fetch('ghostTargetX', 540.0)
        target_y = parent_exec.fetch('ghostTargetY', 540.0)

        GHOST_SPEED = 0.08  # Vitesse d'animation (0.0-1.0)

        # Interpolation
        dx = target_x - current_x
        dy = target_y - current_y
        dist = (dx*dx + dy*dy) ** 0.5

        if dist > 5:  # Pas encore arrivé
            new_x = current_x + dx * GHOST_SPEED
            new_y = current_y + dy * GHOST_SPEED

            parent_exec.store('ghostCurrentX', new_x)
            parent_exec.store('ghostCurrentY', new_y)

            # Envoyer position au HTML
            web = op('webrender1')
            if web:
                js = "if(window.setHeroPosition) window.setHeroPosition({}, {});".format(new_x, new_y)
                try:
                    web.executeJavaScript(js)
                except:
                    pass
        else:
            # Arrivé à destination → cacher le hero
            web = op('webrender1')
            if web:
                js = "if(window.hideHero) window.hideHero();"
                try:
                    web.executeJavaScript(js)
                except:
                    pass
            parent_exec.store('ghostActive', False)


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
# 3. Détection bords: Si x/y = 0 ou 1080, désactive les connexions
# 4. Contrôle HTML: Envoie position au hero ball via JavaScript
# 5. GHOST MODE: Anime le hero vers les boules connectées quand main disparaît
#    - onValueChange: Détecte main inactive → calcule position cible pondérée
#    - whileOff: Anime position chaque frame (GHOST_SPEED = 0.08)
#    - Le système de bridges existant gère la rétractation naturellement via dist
#    - Arrivé à destination → hideHero()
#    - Main revient → ghostActive = False, reprend contrôle normal
#
# =============================================================================
