#include "model_dependent.h"
#include "pic32mx.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>

#define strlen(s) strlen((const char *)(s))
extern "C" {
#include "uart.h"
#include "mrubyc.h"
#include "gpio.h"

// HAL implementations for the simulator
int hal_write(int fd, const void *buf, int nbytes) {
    int res = fwrite(buf, 1, nbytes, stdout);
    fflush(stdout);
    return res;
}

int hal_flush(int fd) {
    (void)fd;
    fflush(stdout);
    return 0;
}

void hal_abort( const char *s ) {
    if( s ) {
        hal_write( 0, s, std::strlen(s) );
    }
    printf("\n\033[91m[SIMULATOR HAL ABORT]\033[0m %s\n", s ? s : "");
    system_reset();
}

void _mon_putc( char c ) {
    fwrite(&c, 1, 1, stdout);
}

static void c_leds_write(mrbc_vm *vm, mrbc_value v[], int argc) {
    int led = GET_INT_ARG(1);
    onboard_led(1, led & 0x01);
    onboard_led(2, led & 0x02);
    onboard_led(3, led & 0x04);
    onboard_led(4, led & 0x08);
}

static void c_sw(mrbc_vm *vm, mrbc_value v[], int argc) {
    SET_INT_RETURN(onboard_sw(1));
}
} // extern "C"
#undef strlen

// mruby/c heap
#if !defined(MRBC_MEMORY_SIZE)
#define MRBC_MEMORY_SIZE (1024*40)
#endif
uint8_t memory_pool[MRBC_MEMORY_SIZE];

static int load_mrb_file(const char* filepath) {
    std::ifstream file(filepath, std::ios::binary | std::ios::ate);
    if (!file.is_open()) {
        printf("\033[91m[SIMULATOR ERROR]\033[0m Failed to open %s\n", filepath);
        return -1;
    }

    std::streamsize size = file.tellg();
    file.seekg(0, std::ios::beg);

    if (size > FAKE_FLASH_SIZE) {
        printf("\033[91m[SIMULATOR ERROR]\033[0m Bytecode size (%ld) exceeds fake flash size (%d)\n", (long)size, FAKE_FLASH_SIZE);
        return -1;
    }

    // Erase needed flash pages
    uint8_t* write_addr = (uint8_t*)FLASH_SAVE_ADDR;
    int pages = (size + FLASH_PAGE_SIZE - 1) / FLASH_PAGE_SIZE;
    for (int i = 0; i < pages; i++) {
        flash_erase_page(write_addr + i * FLASH_PAGE_SIZE);
    }

    // Read file to temp buffer, then write to flash row by row
    uint8_t* buffer = new uint8_t[size];
    if (!file.read((char*)buffer, size)) {
        printf("\033[91m[SIMULATOR ERROR]\033[0m Failed to read from %s\n", filepath);
        delete[] buffer;
        return -1;
    }

    uint8_t* p = buffer;
    int n = size;
    while (n > 0) {
        int chunk = (n < FLASH_ROW_SIZE) ? n : FLASH_ROW_SIZE;
        uint8_t row[FLASH_ROW_SIZE];
        memset(row, 0xFF, FLASH_ROW_SIZE);
        memcpy(row, p, chunk);
        flash_write_row(write_addr, row);
        write_addr += FLASH_ROW_SIZE;
        p += chunk;
        n -= chunk;
    }

    delete[] buffer;

    // Validate the bytecode header
    if (strncmp((const char*)FLASH_SAVE_ADDR, "RITE", 4) != 0) {
        printf("\033[91m[SIMULATOR ERROR]\033[0m Invalid bytecode header (RITE not found)\n");
        return -1;
    }

    printf("\033[92m[SIMULATOR]\033[0m Bytecode loaded successfully (%ld bytes).\n", (long)size);
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        printf("Usage: %s <bytecode.mrb>\n", argv[0]);
        return 1;
    }

    // Make simulator stdout unbuffered so output appears immediately
    setvbuf(stdout, NULL, _IONBF, 0);

    system_init();
    // uart_init();

    if (load_mrb_file(argv[1]) != 0) {
        return 1;
    }

    printf("\033[94m[SIMULATOR]\033[0m Starting mruby/c VM...\n");

    mrbc_init(memory_pool, MRBC_MEMORY_SIZE);

    mrbc_init_class_gpio();
    mrbc_define_method(0, 0, "leds_write", c_leds_write);
    mrbc_define_method(0, 0, "sw", c_sw);

    // Create main task from loaded bytecode
    mrbc_create_task((const void*)FLASH_SAVE_ADDR, 0);

    // Run the VM
    mrbc_run();

    return 0;
}
