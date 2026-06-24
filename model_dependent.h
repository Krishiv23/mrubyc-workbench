/*
  FAKE model_dependent.h -- desktop stand-in for the real PIC32MX170F256B
  model_dependent.h. Macro NAMES match the real repo exactly so that the
  real gpio.c / uart.c / mrbc_firm.c can compile against this unmodified.
  Only the backing implementation is fake.

  Built as C++ (g++ -x c++) so SET/CLR registers can use operator=
  overloading to correctly OR/AND-NOT bits into the real register --
  something a plain C assignment cannot do.
*/
#ifndef MODEL_DEPENDENT_H
#define MODEL_DEPENDENT_H

#include <cstdint>
#include <cstdio>

/* ---------- tiny register proxy types ---------------------------------- */

// "SET" alias: writing X ORs those bits into the real register.
struct RegSet {
    volatile uint32_t *target;
    RegSet &operator=(uint32_t bits) { *target |= bits; return *this; }
    operator uint32_t() const { return *target; }
};

// "CLR" alias: writing X clears those bits from the real register.
struct RegClr {
    volatile uint32_t *target;
    RegClr &operator=(uint32_t bits) { *target &= ~bits; return *this; }
    operator uint32_t() const { return *target; }
};

// TX register: writing a byte immediately "transmits" it (calls a hook).
struct TxRegProxy {
    int unit;
    TxRegProxy &operator=(uint32_t byte);
    operator uint32_t() const { return 0; } // real HW: reading TXREG is meaningless
};

/* ---------- GPIO: 7 ports, A=1 .. G=7 ----------------------------------- */
#define NUM_GPIO_PORTS 7

extern volatile uint32_t REG_ANSEL[NUM_GPIO_PORTS];
extern volatile uint32_t REG_TRIS [NUM_GPIO_PORTS];
extern volatile uint32_t REG_LAT  [NUM_GPIO_PORTS];   // PORTx reads this directly
extern volatile uint32_t REG_ODC  [NUM_GPIO_PORTS];
extern volatile uint32_t REG_CNPU [NUM_GPIO_PORTS];
extern volatile uint32_t REG_CNPD [NUM_GPIO_PORTS];

extern RegSet PROXY_ANSELSET[NUM_GPIO_PORTS];
extern RegClr PROXY_ANSELCLR[NUM_GPIO_PORTS];
extern RegSet PROXY_TRISSET [NUM_GPIO_PORTS];
extern RegClr PROXY_TRISCLR [NUM_GPIO_PORTS];
extern RegSet PROXY_LATSET  [NUM_GPIO_PORTS];
extern RegClr PROXY_LATCLR  [NUM_GPIO_PORTS];
extern RegSet PROXY_ODCSET  [NUM_GPIO_PORTS];
extern RegClr PROXY_ODCCLR  [NUM_GPIO_PORTS];
extern RegSet PROXY_CNPUSET [NUM_GPIO_PORTS];
extern RegClr PROXY_CNPUCLR [NUM_GPIO_PORTS];
extern RegSet PROXY_CNPDSET [NUM_GPIO_PORTS];
extern RegClr PROXY_CNPDCLR [NUM_GPIO_PORTS];

#define ANSELxSET(x)  PROXY_ANSELSET[(x)-1]
#define ANSELxCLR(x)  PROXY_ANSELCLR[(x)-1]
#define TRISxSET(x)   PROXY_TRISSET[(x)-1]
#define TRISxCLR(x)   PROXY_TRISCLR[(x)-1]
#define PORTx(x)      REG_LAT[(x)-1]
#define LATxSET(x)    PROXY_LATSET[(x)-1]
#define LATxCLR(x)    PROXY_LATCLR[(x)-1]
#define ODCxSET(x)    PROXY_ODCSET[(x)-1]
#define ODCxCLR(x)    PROXY_ODCCLR[(x)-1]
#define CNPUxSET(x)   PROXY_CNPUSET[(x)-1]
#define CNPUxCLR(x)   PROXY_CNPUCLR[(x)-1]
#define CNPDxSET(x)   PROXY_CNPDSET[(x)-1]
#define CNPDxCLR(x)   PROXY_CNPDCLR[(x)-1]

// Output pin select table (real chip: lookup table, not arithmetic)
#define RPxnR(x, n)   FAKE_RPxnR[(x)-1][(n)]
extern volatile uint32_t FAKE_RPxnR[NUM_GPIO_PORTS][16];

/* ---------- UART: 2 units --------------------------------------------- */
#define NUM_UART_UNIT 2

extern volatile uint32_t REG_UMODE[NUM_UART_UNIT];
extern volatile uint32_t REG_USTA [NUM_UART_UNIT];
extern volatile uint32_t REG_UBRG [NUM_UART_UNIT];
extern volatile uint32_t REG_URXREG[NUM_UART_UNIT];

extern RegSet     PROXY_UMODESET[NUM_UART_UNIT];
extern RegClr      PROXY_UMODECLR[NUM_UART_UNIT];
extern RegSet      PROXY_USTASET[NUM_UART_UNIT];
extern RegClr      PROXY_USTACLR[NUM_UART_UNIT];
extern TxRegProxy  PROXY_UTXREG[NUM_UART_UNIT];

#define UxMODE(x)     REG_UMODE[(x)-1]
#define UxMODESET(x)  PROXY_UMODESET[(x)-1]
#define UxMODECLR(x)  PROXY_UMODECLR[(x)-1]
#define UxSTA(x)      REG_USTA[(x)-1]
#define UxSTASET(x)   PROXY_USTASET[(x)-1]
#define UxSTACLR(x)   PROXY_USTACLR[(x)-1]
#define UxTXREG(x)    PROXY_UTXREG[(x)-1]
#define UxRXREG(x)    REG_URXREG[(x)-1]
#define UxBRG(x)      REG_UBRG[(x)-1]
#define UxRXR(x)      FAKE_URXR[(x)-1]
extern volatile uint32_t FAKE_URXR[NUM_UART_UNIT];

// Status bits actually referenced by uart.c (subset of real XC32 names)
#define _U1STA_UTXEN_MASK   0x0400
#define _U1STA_URXEN_MASK   0x1000
#define _U1STA_UTXBF_MASK   0x0200
#define _U1STA_TRMT_MASK    0x0100
#define _U1STA_UTXBRK_MASK  0x0800
#define _U1MODE_ON_MASK     0x8000
#define _U1MODE_PDSEL_MASK  0x0600
#define _U1MODE_PDSEL_POSITION 9
#define _U1MODE_STSEL_POSITION 0

#define IPC_U1IPIS(ip, is)  ((void)0)
#define IPC_U2IPIS(ip, is)  ((void)0)

/* default pin assign (unused on desktop, kept for source compatibility) */
#define UART1_TXD_PIN  2,4
#define UART1_RXD_PIN  1,4
#define UART2_TXD_PIN  2,9
#define UART2_RXD_PIN  2,8
#define UART_CONSOLE   1

/* ---------- fake flash (lets mrbc_firm.c dereference these directly) --- */
#define FLASH_PAGE_SIZE 1024
#define FLASH_ROW_SIZE  (FLASH_PAGE_SIZE / 8)
#define FLASH_ALIGN_ROW_SIZE(bytes) \
  ((bytes) + ((FLASH_ROW_SIZE - (bytes)) & (FLASH_ROW_SIZE-1)))
#define FAKE_FLASH_SIZE (32 * 1024)

extern uint8_t FAKE_FLASH[FAKE_FLASH_SIZE];
#define FLASH_SAVE_ADDR ((uintptr_t)FAKE_FLASH)
#define FLASH_END_ADDR  (FLASH_SAVE_ADDR + FAKE_FLASH_SIZE - 1)

/* ---------- clock ------------------------------------------------------ */
#define _XTAL_FREQ 40000000UL
#define PBCLK (_XTAL_FREQ / 4)

void system_init(void);
void onboard_led(int num, int on_off);
int  onboard_sw(int num);

/* Test-harness hooks (not part of the real repo, ours only) */
void pic32emu_uart_set_tx_hook(void (*hook)(int unit, uint8_t byte));
void pic32emu_dump_gpio_state(void);
void pic32emu_register_reset_hook(void (*hook)(void));

#endif /* MODEL_DEPENDENT_H */
