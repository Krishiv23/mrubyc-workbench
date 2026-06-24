/*
  Backing storage for model_dependent.h's fake registers, and the
  desktop-native reimplementations of pic32mx.c's chip-control functions
  (delays, system reset, flash). These replace the real pic32mx.c body --
  it contains inline MIPS assembly and CP0 cycle counting that simply
  cannot compile on a desktop CPU, so rather than fake the silicon
  underneath it, we give the same function signatures new bodies.
*/
#include "model_dependent.h"
#include "pic32mx.h"
#include <cstdio>
#include <cstring>
#include <ctime>
#include <cstdlib>
#include <chrono>
#include <thread>

/* ---------- GPIO backing storage --------------------------------------- */
volatile uint32_t REG_ANSEL[NUM_GPIO_PORTS] = {0};
volatile uint32_t REG_TRIS [NUM_GPIO_PORTS] = {0};
volatile uint32_t REG_LAT  [NUM_GPIO_PORTS] = {0};
volatile uint32_t REG_ODC  [NUM_GPIO_PORTS] = {0};
volatile uint32_t REG_CNPU [NUM_GPIO_PORTS] = {0};
volatile uint32_t REG_CNPD [NUM_GPIO_PORTS] = {0};
volatile uint32_t FAKE_RPxnR[NUM_GPIO_PORTS][16] = {{0}};

#define BANK(name, target_array) \
    name[NUM_GPIO_PORTS] = { \
        {&target_array[0]}, {&target_array[1]}, {&target_array[2]}, \
        {&target_array[3]}, {&target_array[4]}, {&target_array[5]}, \
        {&target_array[6]} }

RegSet BANK(PROXY_ANSELSET, REG_ANSEL);
RegClr BANK(PROXY_ANSELCLR, REG_ANSEL);
RegSet BANK(PROXY_TRISSET,  REG_TRIS);
RegClr BANK(PROXY_TRISCLR,  REG_TRIS);
RegSet BANK(PROXY_LATSET,   REG_LAT);
RegClr BANK(PROXY_LATCLR,   REG_LAT);
RegSet BANK(PROXY_ODCSET,   REG_ODC);
RegClr BANK(PROXY_ODCCLR,   REG_ODC);
RegSet BANK(PROXY_CNPUSET,  REG_CNPU);
RegClr BANK(PROXY_CNPUCLR,  REG_CNPU);
RegSet BANK(PROXY_CNPDSET,  REG_CNPD);
RegClr BANK(PROXY_CNPDCLR,  REG_CNPD);
#undef BANK

/* ---------- UART backing storage --------------------------------------- */
volatile uint32_t REG_UMODE[NUM_UART_UNIT]  = {0};
volatile uint32_t REG_USTA [NUM_UART_UNIT]  = {_U1STA_TRMT_MASK}; // start "idle/done"
volatile uint32_t REG_UBRG [NUM_UART_UNIT]  = {0};
volatile uint32_t REG_URXREG[NUM_UART_UNIT] = {0};
volatile uint32_t FAKE_URXR[NUM_UART_UNIT]  = {0};

RegSet PROXY_UMODESET[NUM_UART_UNIT] = { {&REG_UMODE[0]}, {&REG_UMODE[1]} };
RegClr PROXY_UMODECLR[NUM_UART_UNIT] = { {&REG_UMODE[0]}, {&REG_UMODE[1]} };
RegSet PROXY_USTASET [NUM_UART_UNIT] = { {&REG_USTA[0]},  {&REG_USTA[1]} };
RegClr PROXY_USTACLR [NUM_UART_UNIT] = { {&REG_USTA[0]},  {&REG_USTA[1]} };
TxRegProxy PROXY_UTXREG[NUM_UART_UNIT] = { {0}, {1} };

static void (*g_uart_tx_hook)(int unit, uint8_t byte) = nullptr;

void pic32emu_uart_set_tx_hook(void (*hook)(int unit, uint8_t byte)) {
    g_uart_tx_hook = hook;
}

// Default behaviour if no test-harness hook is registered: print it.
static void default_tx_hook(int unit, uint8_t byte) {
    printf("\033[96m[UART%d TX]\033[0m 0x%02X '%c'\n",
           unit + 1, byte, (byte >= 32 && byte < 127) ? byte : '.');
}

TxRegProxy &TxRegProxy::operator=(uint32_t byte) {
    // Real hardware: shift register drains the FIFO over time. On a
    // desktop there's no real timing to model, so the byte is "sent"
    // immediately and the busy/done status bits never need to go busy.
    if (g_uart_tx_hook) g_uart_tx_hook(unit, (uint8_t)byte);
    else default_tx_hook(unit, (uint8_t)byte);
    return *this;
}

/* ---------- fake flash -------------------------------------------------- */
uint8_t FAKE_FLASH[FAKE_FLASH_SIZE];

unsigned int NVMUnlock(unsigned int /*nvmop*/) {
    return 0; // desktop: never fails
}

unsigned int flash_erase_page(void *address) {
    uintptr_t off = (uintptr_t)address - FLASH_SAVE_ADDR;
    if (off >= FAKE_FLASH_SIZE) {
        printf("\033[91m[FLASH FAULT] erase address out of range\033[0m\n");
        return 1;
    }
    memset(FAKE_FLASH + off, 0xFF, FLASH_PAGE_SIZE); // erased flash reads as 0xFF
    printf("\033[93m[FLASH]\033[0m erased page at offset 0x%04zx\n", (size_t)off);
    return 0;
}

unsigned int flash_write_row(void *address, void *data) {
    uintptr_t off = (uintptr_t)address - FLASH_SAVE_ADDR;
    if (off >= FAKE_FLASH_SIZE) {
        printf("\033[91m[FLASH FAULT] write address out of range\033[0m\n");
        return 1;
    }
    memcpy(FAKE_FLASH + off, data, FLASH_ROW_SIZE);
    printf("\033[93m[FLASH]\033[0m wrote row at offset 0x%04zx\n", (size_t)off);
    return 0;
}

/* ---------- delays ------------------------------------------------------ */
void __delay_us(uint32_t us) {
    std::this_thread::sleep_for(std::chrono::microseconds(us));
}

void __delay_ms(uint32_t ms) {
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}

/* ---------- system control ---------------------------------------------- */
void system_register_lock(void)   { /* no-op: no protected SFRs to guard */ }
void system_register_unlock(void) { /* no-op: no protected SFRs to guard */ }

static void (*g_reset_hook)(void) = nullptr;
void pic32emu_register_reset_hook(void (*hook)(void)) { g_reset_hook = hook; }

void system_reset(void) {
    printf("\033[91m[SIMULATED RESET]\033[0m chip would restart here.\n");
    if (g_reset_hook) { g_reset_hook(); return; }
    exit(0);
}

/* ---------- board-level stubs (no real onboard LEDs/switches on a laptop) */
void system_init(void) {
    printf("\033[94m[EMU INIT]\033[0m Virtual PIC32MX170F256B platform ready.\n");
}
void onboard_led(int num, int on_off) {
    printf("\033[93m[BOARD LED]\033[0m LED%d -> %s\n", num, on_off ? "ON" : "OFF");
}
int onboard_sw(int /*num*/) { return 0; }

/* ---------- debug helper ------------------------------------------------ */
void pic32emu_dump_gpio_state(void) {
    static const char *names = "ABCDEFG";
    printf("\n--- GPIO STATE ---\n");
    for (int i = 0; i < NUM_GPIO_PORTS; i++) {
        if (REG_TRIS[i] || REG_LAT[i] || REG_ANSEL[i]) {
            printf("Port %c: TRIS=0x%04X LAT=0x%04X ANSEL=0x%04X\n",
                   names[i], REG_TRIS[i], REG_LAT[i], REG_ANSEL[i]);
        }
    }
    printf("------------------\n");
}
