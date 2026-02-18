# FaceCommand
Webcam-based facial gesture macro tool written in python

Run fc_install to install dependencies 

Features: 

Webcam feed with zoom and pan

  -can be recalibrated if readings drift
  
Live gesture readings

12 distinct gestures recognized 

  -Eyebrow raise (works independently from left and right)
  
  -Right eyebrow raise
  
  --Special feature: The Rock
    
  -Left eyebrow raise
  
  -Brow furrow 
  
  -Blink 
  
  -Wink right 
  
  -Wink Left
  
  -Smile
  
  -Open mouth
  
  -Pucker
  
  -Smirk right
  
  -Smirk left
  
Global settings for: 
  
  -hold time for trigger 
  
  -cooldown 
  
  -smoothing
  
  -head tilt compensation (in progress)
  
Each gesture has its own trigger thresholds and sensitivity (in progress)
  
  -trigger actions can be key presses, mouse functions, and macros that combine both
  
  -trigger mode can be single press, hold for x(ms), and toggle 

Gesture Chains allow for sequences of gestures to trigger a single command or macro (like power moves in a fighting game); this is useful for:
  
  -expanding the commands beyond 12
  
  -eliminating accidental triggers of critical commands

Morse Chains allow a single gesture to trigger unlimited commands via short and long holds 

Profile export/import

While it's possible to use all of the gestures simultaneously, there is still some crosstalk between certain gestures that move similar parts of the face. This is especially true when moving your head around. This will be improved as I incorporate more head orientation compensation and better sensitivity control. I want to include as many gestures as possible because people have different abilities to control their face. Even with just a few gestures, many commands can be made with the Gesture Chains tool.

Future features:

-Each gesture having its own hold time and cooldown

-Connection to virtual controllers for analog input

-Cursor control with head movement 
