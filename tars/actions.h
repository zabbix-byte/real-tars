#pragma once
#include <Arduino.h>

// Acciones fisicas / motoras de TARS.
//
// HOY: TARS no tiene ruedas ni servos. Estas funciones solo loguean por serie
// y opcionalmente notifican por Telegram. La intencion es tener la API ya lista
// para que cuando llegue el chasis solo haya que rellenar las implementaciones
// reales (PWM motores, PCA9685 servos, etc.) sin tocar el resto del codigo.

namespace actions {
    void approachUser();   // "ven aqui" -> ir hacia el usuario
    void halt();           // "para" -> detener cualquier movimiento
    void wander();         // "explora" -> deambular curioseando
    void sleep();          // "descansa" -> bajo consumo
    void playMode();       // "diviertete" -> movimientos juguetones
    void lookHere();       // "mira" -> apuntar la cabeza al frente / al sonido
}
