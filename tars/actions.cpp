#include "actions.h"
#include "config.h"

namespace actions {

// TODO: cuando llegue el hardware, sustituir cada Serial.println por el
// codigo real (PWM motores, servos, LEDs, etc.).

void approachUser() {
    Serial.println("[ACT] approachUser() -> motor::moveTowardsSound() [stub]");
}

void halt() {
    Serial.println("[ACT] halt() -> motor::stop() [stub]");
}

void wander() {
    Serial.println("[ACT] wander() -> motor::randomWalk() [stub]");
}

void sleep() {
    Serial.println("[ACT] sleep() -> low power, eyes dim [stub]");
}

void playMode() {
    Serial.println("[ACT] playMode() -> servos jiggle, LEDs party [stub]");
}

void lookHere() {
    Serial.println("[ACT] lookHere() -> head pan/tilt center [stub]");
}

} // namespace actions
