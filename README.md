# gdsfactory_projects
Projects for gdsfactory and testing

Project 1: Hello World Example
-- This is in this folder labeled "helloworld.py"
-- You can run it with klayout browser open with klive and it should display it
-- There is also an image of it

Project 2: PCell and SAX Model
-- I created a PCell model for the pmos cell in the IHP PDK in "modular_pmos.py"
-- I have setup this docker and toolchain: https://github.com/iic-jku/IIC-OSIC-TOOLS
-- I then created a pcell using klayout in the docker container and then copied over the gds to this repo (did a lot of variations)
-- You can use the "compare.py" file to run gds comparisons using XOR method
-- I also created a SAX Model of the pmos transistor in "saxmodel.py"

Project 3: RF Circuit Design
-- I haven't gotten around to fully creating one design yet
-- Having lots of troubles with integrating the IHP PDK with NGSPICE, GDSFACTORY, and PySpice
-- Current Progress:
-- 1. Have installed IHP PDK and NGSPICE manually and setup all the environment variables and files to run them nicely
-- 2. Have verified that PySpice is working with NGSPICE through the PySpice basic resistor simulation examples ("voltage_divider_ex.py")
-- 3. Have created a basic Yaml circuit to test and simulate
--      a. The GDSFactory integration and extraction of that netlist somewhat works with IHP PDK components
--      -- (Still very buggy and the routing strategies weren't working so I created one of my own to make it somewhat work)
--      -- You can run "yamltest.py" to get the gdsfactory klayout from the yaml files
-- 4. PySpice integration and simulations with IHP PDK components isn't workly nicely and still debugging and fixing
--      a. Working on "IHP_HBT_DC_curves.py" to get all the DC curves of the IHP component and make sure it is working nicely
--          i. Have the Vbe vs Ic curve working but not the others yet
--      b. Will make an actual RFIC circuit after verifying simulations work and data is accurate

Project 4: RF Models
-- Have 0 progress on this task to create an RF model like an LC oscillator Josephson Junction Model
-- Will come to this after figuring out RF simulations with PySpice

Project 5: Interface with Other Tools
-- Haven't really added any new extensions
-- Currently planning on adding a small extension or plugin to easily convert a gdsfactory yaml file to a PySpice netlist and simulate it
-- Working on this concurrently with Project 3 and almost done
-- I can bypass the RF simulation and just work on the plugin but want to make Project 3 work first

Bugs / Errors I have run into
-- 1. Lots of errors (width, type mismatch) in the layout routing functions for the electrical IHP PDK in gdsfactory
--      a. Won't let me read the yaml files nicely without proper connections
-- 2. Bug in properly converting yaml to layout (first routing function call doesn't connect the defined components correctly)
-- 3. Lots of errors in the PySpice implementation of IHP devices (only works with HBTs since they are VBIR models?)
--      a. the error stems from ngspice osdi Verilog models not being parsed correctly by pySpice and read
--      b. when I tried importing the osdi files directly before the netlist, it gives some label errors
--      c. Bypassed all these bugs and errors through functions and parsing all stdout calls from NGSPICE
-- 4. Overall PySpice doesn't integrate nicely with IHP components and am currently working on finding out fixes and hopefully clean up messy code


Certain Bug Fixes:
-- If you get the command "run" failed error with PySpice:
-- If you absolutely must use the shared library, you have to tell PySpice to stop being so sensitive to "stderr" (error) messages.

-- Find where PySpice is installed:
-- Type in Bash: "pip show PySpice"
-- Navigate to that directory and find Spice/NgSpice/Shared.py.
-- Look for the exec_command function (around line 850).
-- You will see a block that raises NgSpiceCommandError if there is any output in the error log. Comment out that raise line.
