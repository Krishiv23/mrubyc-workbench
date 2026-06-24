/*! @file
  @brief
  Include at once the necessary header files.

  <pre>
  Copyright (C) 2015- Kyushu Institute of Technology.
  Copyright (C) 2015- Shimane IT Open-Innovation Center.

  This file is distributed under BSD 3-Clause License.

  </pre>
*/

#ifndef MRBC_SRC_MRUBYC_H_
#define MRBC_SRC_MRUBYC_H_

//@cond
#ifdef __cplusplus
extern "C" {
#endif
#include "vm_config.h"
#ifdef __cplusplus
}
#endif
#include "hal.h"

#include "alloc.h"
#include "value.h"

#include "symbol.h"
#include "error.h"
#include "keyvalue.h"

#include "global.h"
#include "class.h"

#include "vm.h"
#include "load.h"
#include "console.h"

#include "c_numeric.h"
#include "c_object.h"
#include "c_array.h"
#include "c_string.h"
#include "c_range.h"
#include "c_hash.h"
#include "c_math.h"

#include "rrt0.h"
//@endcond

#endif
