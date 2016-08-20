// Receives a command in the form of an ascii string
// "command_name integer_argument integer_argument ... integer_argument#optional_checksum_hex\r"
// (the '#' is there only if a checksum is provided)
// executes the command
// and returns an ascii string
// "original_command#command_checksum_hex\r\n\x04integer_return integer_return ... integer_return#return_checksum_hex\r\n\x04".
// If commands do not produce return values, the string "0" with a checksum is returned to signify
// success.

// If an incomming message has an incorrect checksum a "\r\n-\r\n" is returned without a checksum.

// There is no way for an outgoing message to be repeated if the peer got an incorrect checksum.

// A watchdog is present. If no "checkHeartBeat" is received for longer than 4 seconds it resets the board.
// Hence a heartbeat command is necessary. On a watchdog reset a "\r\nready\r\n" message is sent.
// A peer that received a bad message can just wait for a "\r\nready\r\n" message and retry.

// If the checksum of an incomming message is longer or shorter than 8 characters long, it is
// still read from the serial buffer, however it is simply assumed wrong. That way no garbage is
// left in the buffer for the next round of command parsing.

// A lot of stuff is done with string representations of numbers instead of raw ints for the sake
// of humans using this interactively. For the same reason we need echo (which stops us from using
// many of the Arduino builtin methods).

#include <FastCRC.h>
#include <stdlib.h>
#include <avr/wdt.h>
#include <MemoryFree.h>
#include <Stepper.h>
#include <OneWire.h>
#include <DallasTemperature.h>

#define SERIAL_SPEED 9600
#define ECHO true
#define WATCHDOG false

String buf = ""; // contains the received command
char crc[8];     // contains the received checksum of the command as hex representation of a 32bit number

FastCRC32 CRC32; // module for calculating crc checksums
// CRC32 is a ridiculous overkill, but it is in the python standard library.

void setup() {
  wdt_disable();
  Serial.begin(SERIAL_SPEED);
  Serial.println();
  Serial.println("ready");
  Serial.write(4); // ascii EOT
  buf.reserve(100);
  setupComponents();
  if (WATCHDOG) {
    wdt_enable(WDTO_4S);
  }
  wdt_reset();
}

void loop() { // each run of `loop` waits for one command, parses and executes it, prints its output, and returns
  buf = "";
  char inByte;
  while (true) {                    // looping until we receive a delimiter character or the watchdog kills us
      inByte = busyRead();          // read one character

      if (inByte == '\r') {         // if the delimiter character, the data has been received, do something with it
        printWithCRC(buf);
        executeCommand();
        return;
      }

      else if (inByte == '#') {     // if the character signifying a checksum is present, read and verify the checksum
        size_t i=0;
        while (i<8) {
          crc[i] = busyRead();
          if (crc[i] == '\r') { 
            reportError();
            return;
          }
          i += 1;
        }
                                    // if the checksum does not match, cancel this comand
        if (CRC32.crc32((uint8_t *)buf.c_str(), buf.length()) != strtoul(crc, NULL, 16)) { // convert the checksum string back to an integer and compare to the calculated checksum
          clearRemainingChars();
          reportError();
          return;
        }

        inByte = busyRead();        // read one character
        if (inByte == '\r') {       // if the delimiter character, the data has been received, do something with it
          printWithCRC(buf);
          executeCommand();
          return;
        } else {
          clearRemainingChars();
          reportError();
          return;
        }

      }

      else {                        // if it is just a normal character, add it to the buffer in preparation for interpreting it
        buf += inByte;
      }

    }
}

void printWithCRC(String msg) { // TODO Subclass Serial
  Serial.println();
  Serial.print(msg);
  Serial.print("#");
  Serial.println(CRC32.crc32((uint8_t *)msg.c_str(), msg.length()), HEX);
  Serial.write(4); // ascii EOT
}

char busyRead() {
  while (Serial.available()==0) {}
  char inByte = Serial.read();
  if (ECHO) { // if set, echo the character back, so we see what we type
    Serial.write(inByte);
  }
  return inByte;
}

void clearRemainingChars() {
  char inByte; 
  while (true) {
    inByte = busyRead();
    if (inByte == '\r') {
      break;
    }
  }
}

void reportError() {
  Serial.println();
  Serial.println("-"); 
  Serial.write(4); // ascii EOT
}

void executeCommand() { // TODO Write a dispatcher class
  if (buf == "checkHeartBeat") {
    checkHeartBeat();
    wdt_reset();
  }

  else if (buf.startsWith("anRead")) {
    anRead();
  }

  else if (buf.startsWith("anWrite")) {
    anWrite();  
  }

  else if (buf.startsWith("moveStepper")) {
    moveStepper();
  }

  else if (buf.startsWith("checkOrigin")) {
    checkOrigin();
  }

  else if (buf.startsWith("getTemperatures")) {
    getTemperatures();
  }

  else if (buf.startsWith("setHeatFlow")) {
    setHeatFlow();
  }

  else {
    reportError();
  }
  
}

////////////////////////////////////////////////////////////////////////////
// Commands' implementation.
////////////////////////////////////////////////////////////////////////////

Stepper stepperx(4096, 23, 25, 27, 29);
Stepper steppery(4096, 28, 26, 24, 22);
int originx = 53;
int originy = 52;

OneWire oneWire(33);
DallasTemperature sensors(&oneWire);
DeviceAddress temp0 = {0x28, 0x2D, 0x6D, 0x55, 0x07, 0x00, 0x00, 0x3C};
DeviceAddress temp1 = {0x28, 0x28, 0xB8, 0x56, 0x07, 0x00, 0x00, 0xD3};
DeviceAddress temp2 = {0x28, 0x38, 0xB2, 0x55, 0x07, 0x00, 0x00, 0xBD};
DeviceAddress temp3 = {0x28, 0xF1, 0xAD, 0x56, 0x07, 0x00, 0x00, 0x2F};
DeviceAddress temp4 = {0x28, 0xC8, 0xC8, 0x55, 0x07, 0x00, 0x00, 0x1F};
DeviceAddress temp5 = {0x28, 0xDB, 0xFA, 0x55, 0x07, 0x00, 0x00, 0x1A};

int coolA = 2;
int heatA = 3;
int heatB = 4;
int coolB = 5;
int fan = 7;

void setupComponents() {
  stepperx.setSpeed(2);
  steppery.setSpeed(2);
  pinMode(originx, INPUT_PULLUP);
  pinMode(originy, INPUT_PULLUP);
  sensors.setResolution(temp0, 11);
  sensors.setResolution(temp1, 11);
  sensors.setResolution(temp2, 11);
  sensors.setResolution(temp3, 11);
  sensors.setResolution(temp4, 11);
  sensors.setResolution(temp5, 11);
  sensors.setWaitForConversion(true);
  pinMode(coolA, OUTPUT);
  pinMode(heatA, OUTPUT);
  pinMode(heatB, OUTPUT);
  pinMode(coolB, OUTPUT);
  pinMode(fan, OUTPUT);
  digitalWrite(coolA, LOW);
  digitalWrite(heatA, LOW);
  digitalWrite(heatB, LOW);
  digitalWrite(coolB, LOW);
  digitalWrite(fan, LOW);
}

void moveStepper() {
  int index = buf.indexOf(' ');
  if (buf[index+1] == 'x') {
    if (buf[index+3] == '+') stepperx.step(10);
    if (buf[index+3] == '-') stepperx.step(-10);
  }
  else {
    if (buf[index+3] == '+') steppery.step(10);
    if (buf[index+3] == '-') steppery.step(-10);
  }
  printWithCRC("0");
}

void checkOrigin() {
  String ret = "";
  ret += digitalRead(originx);
  ret += ' ';
  ret +=digitalRead(originy);
  printWithCRC(ret);
}

void getTemperatures() {
  String ret = "";
  sensors.requestTemperatures();
  ret += sensors.getTempC(temp0);
  ret += ' ';
  ret += sensors.getTempC(temp1);
  ret += ' ';
  ret += sensors.getTempC(temp2);
  ret += ' ';
  ret += sensors.getTempC(temp3);
  ret += ' ';
  ret += sensors.getTempC(temp4);
  ret += ' ';
  ret += sensors.getTempC(temp5);
  printWithCRC(ret);
}

void setHeatFlow() {
  int index = buf.indexOf(' ');
  int flow = buf.substring(index + 1).toInt();
  if (flow >= 0) {
    analogWrite(coolA, 0);
    analogWrite(coolB, 0);
    analogWrite(heatA, flow);
    analogWrite(heatB, flow);
    digitalWrite(fan, LOW);
  }

  else {
    analogWrite(heatA, 0);
    analogWrite(heatB, 0); 
    analogWrite(coolA, -flow);
    analogWrite(coolB, -flow);
    digitalWrite(fan, HIGH);     
  }
  
  printWithCRC("0");
}

void checkHeartBeat() {
  String ret = "";
  ret += millis();
  ret += ' ';
  ret += freeMemory();
  printWithCRC(ret);
}

void anRead() {
  int index = buf.indexOf(' ');
  int pin = buf.substring(index + 1).toInt();
  String ret = "";
  ret += analogRead(pin);
  printWithCRC(ret);
}

void anWrite() {
  int index1 = buf.indexOf(' ');
  int index2 = buf.indexOf(' ', index1 + 1);
  int pin = buf.substring(index1 + 1, index2).toInt();
  int value = buf.substring(index2 + 1).toInt();
  analogWrite(pin, value);
  printWithCRC("0");
}
