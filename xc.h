#ifndef XC_H
#define XC_H

/* 
 * Dummy xc.h for desktop simulator.
 */

#ifdef __cplusplus
#include "pic32mx.h"
#else
// For pure C files (mruby/c VM source), provide stubs so they don't need C++ headers
#define __delay_ms(x) ((void)(x))
#endif

// Define built-in interrupt stubs so hal.h doesn't error out
#define __builtin_enable_interrupts()  ((void)0)
#define __builtin_disable_interrupts() ((void)0)
#define _wait()                        ((void)0)
#define Nop()                          ((void)0)

#endif
