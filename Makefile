CXX = g++
CC = gcc
CFLAGS = -std=c11 -Wall -Wextra -D__PIC32MX170F256B__ -DMRBC_NO_TIMER -D_USE_MATH_DEFINES -I. -Ipic32mx170_mrubyc-master/pic32mx170_mrubyc-master -Ipic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src
CXXFLAGS = -std=c++17 -Wall -Wextra -D__PIC32MX170F256B__ -DMRBC_NO_TIMER -D_USE_MATH_DEFINES -I. -Ipic32mx170_mrubyc-master/pic32mx170_mrubyc-master -Ipic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src

TARGET = simulator

# Platform and Simulator C++ files
CXX_SRCS = model_dependent.cpp simulator_main.cpp

# Hardware interaction C files (must be compiled as C++ for proxy objects)
CPP_C_SRCS = \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/gpio.c

# mruby/c VM source (pure C)
C_SRCS = \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/alloc.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/c_array.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/c_hash.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/c_math.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/c_numeric.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/c_object.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/c_proc.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/c_range.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/c_string.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/class.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/console.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/error.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/global.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/keyvalue.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/load.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/mrblib.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/rrt0.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/symbol.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/value.c \
	pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/vm.c

OBJS = $(CXX_SRCS:.cpp=.o) $(CPP_C_SRCS:.c=.o) $(C_SRCS:.c=.o)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) $(OBJS) -o $(TARGET)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(CPP_C_SRCS:.c=.o): %.o: %.c
	$(CXX) $(CXXFLAGS) -x c++ -c $< -o $@

$(C_SRCS:.c=.o): %.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	powershell -Command "Remove-Item -Force $(TARGET).exe, *.o, pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/*.o, pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/src/*.o -ErrorAction SilentlyContinue"

.PHONY: clean
