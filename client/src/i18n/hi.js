/**
 * Hindi for the patient screens. Keys are the exact English text (app labels and server text alike);
 * HI_PATTERNS handles text with numbers or names in it. Medical terms keep the common English word in brackets
 * where Hindi speakers usually know the English one better (bpm, ECG).
 */
export const HI = {
  // shell
  'Aura Screen': 'ऑरा स्क्रीन',
  'Scan Hub': 'स्कैन हब',
  'Session Report': 'सत्र रिपोर्ट',
  'Biometric Timeline': 'बायोमेट्रिक टाइमलाइन',
  Scan: 'स्कैन',
  Report: 'रिपोर्ट',
  Timeline: 'टाइमलाइन',
  'Sign out': 'साइन आउट',
  'Aura biometrics': 'ऑरा बायोमेट्रिक्स',
  'Biometric screening': 'बायोमेट्रिक जाँच',
  'Your results': 'आपके परिणाम',
  'Past sessions': 'पिछले सत्र',
  'Scan to begin': 'शुरू करने के लिए स्कैन करें',
  'Active session': 'चालू सत्र',
  'Set up your record': 'अपना रिकॉर्ड बनाएँ',
  'Sign in': 'साइन इन',
  Welcome: 'स्वागत है',
  Close: 'बंद करें',
  'Date not recorded': 'तारीख दर्ज नहीं',
  Language: 'भाषा',
  'Colour-blind mode': 'रंग-अंधता मोड',
  Colours: 'रंग',
  'Normal colours': 'सामान्य रंग',
  'Colour-blind safe colours': 'रंग-अंधता के लिए सुरक्षित रंग',
  'Preview: protanopia (red-blind)': 'झलक: प्रोटानोपिया (लाल रंग न दिखना)',
  'Preview: deuteranopia (green-blind)': 'झलक: ड्यूटेरानोपिया (हरा रंग न दिखना)',

  // scan hub
  'Hello,': 'नमस्ते,',
  'How is your body feeling today?': 'आज आपका शरीर कैसा महसूस कर रहा है?',
  'bpm · last read': 'bpm · पिछली रीडिंग',
  'Facial micro-pulse and breath cadence sensors are primed for a contactless read at Station 2.':
    'स्टेशन 2 पर बिना छुए जाँच के लिए चेहरे की नब्ज़ और साँस की लय के सेंसर तैयार हैं।',
  'Begin contactless scan': 'बिना छुए स्कैन शुरू करें',
  'Last screening': 'पिछली जाँच',
  'all readings in normal harmony': 'सभी रीडिंग सामान्य',
  Cleared: 'ठीक पाया गया',
  Pulse: 'नब्ज़',
  Temp: 'तापमान',
  Resp: 'साँस',
  'What the station captures': 'स्टेशन क्या रिकॉर्ड करता है',
  'Consent summary': 'सहमति का सारांश',
  'How it works': 'यह कैसे काम करता है',
  Consent: 'सहमति',
  'Consent given 12 Aug 2026 for contactless screening at Central Diagnostic Centre and Northside Clinic. Withdraw mid-session and nothing is written; revoke later in Profile and records are deleted within 24 hours.':
    '12 अगस्त 2026 को सेंट्रल डायग्नोस्टिक सेंटर और नॉर्थसाइड क्लिनिक में बिना छुए जाँच के लिए सहमति दी गई। सत्र के बीच में हटें तो कुछ भी सेव नहीं होता; बाद में प्रोफ़ाइल में सहमति वापस लें तो 24 घंटे में रिकॉर्ड मिटा दिए जाते हैं।',
  'Face video': 'चेहरे का वीडियो',
  'Processed on the station itself. Never stored.': 'स्टेशन पर ही प्रोसेस होता है। कभी सेव नहीं होता।',
  'Thermal image': 'थर्मल तस्वीर',
  'One frame, retained for 90 days.': 'एक फ़्रेम, 90 दिन तक रखा जाता है।',
  'ECG trace — optional': 'ECG ट्रेस — वैकल्पिक',
  'Only when the contactless signal is weak.': 'सिर्फ़ तब जब बिना छुए मिला सिग्नल कमज़ोर हो।',
  optimal: 'उत्तम',

  // active scan
  Positioning: 'सही जगह पर',
  Capturing: 'रिकॉर्ड हो रहा है',
  ECG: 'ECG',
  Analysing: 'विश्लेषण हो रहा है',
  Done: 'पूरा',
  'analysing readings': 'रीडिंग का विश्लेषण',
  'seconds remaining': 'सेकंड बाकी',
  'Capture complete': 'रिकॉर्डिंग पूरी',
  'Breathe gently, face forward': 'धीरे साँस लें, चेहरा सामने रखें',
  'Keep your expression relaxed inside the illuminated halo. No numbers are shown until the capture completes.':
    'रोशनी वाले घेरे के अंदर चेहरा शांत रखें। रिकॉर्डिंग पूरी होने तक कोई संख्या नहीं दिखाई जाती।',
  'Your readings are being analysed. Your session report will be ready shortly.':
    'आपकी रीडिंग का विश्लेषण हो रहा है। आपकी सत्र रिपोर्ट जल्द तैयार होगी।',
  'View session report': 'सत्र रिपोर्ट देखें',
  'Back to Scan Hub': 'स्कैन हब पर वापस',
  'Signal quality': 'सिग्नल की गुणवत्ता',
  Lighting: 'रोशनी',
  Position: 'स्थिति',
  Motion: 'हलचल',
  Signal: 'सिग्नल',
  'Centered aura': 'घेरे के बीच में',
  'Calibrated · still': 'सेट · स्थिर',
  'ECG fallback': 'ECG विकल्प',
  'if the contactless signal stays weak, the session asks for both index fingers on the station pads for 20 seconds.':
    'अगर बिना छुए मिला सिग्नल कमज़ोर रहे, तो सत्र 20 सेकंड के लिए दोनों तर्जनी उँगलियाँ स्टेशन के पैड पर रखने को कहेगा।',
  'Conditional step': 'ज़रूरत पर चरण',
  'Cancel session': 'सत्र रद्द करें',

  // camera / QR
  'Waking the camera…': 'कैमरा चालू हो रहा है…',
  'Point your camera at the station QR code': 'कैमरा स्टेशन के QR कोड की ओर करें',
  'Checking the code…': 'कोड जाँचा जा रहा है…',
  'Station verified': 'स्टेशन की पुष्टि हुई',
  'The camera could not start': 'कैमरा शुरू नहीं हो सका',
  'Allow camera access when your browser asks.': 'ब्राउज़र पूछे तो कैमरा की अनुमति दें।',
  'Hold steady — this connects your session to the station automatically.':
    'स्थिर रखें — इससे आपका सत्र अपने आप स्टेशन से जुड़ जाएगा।',
  'Making sure it comes from an Aura Screen kiosk.': 'जाँच रहे हैं कि यह ऑरा स्क्रीन कियोस्क का है।',
  'You can still continue — staff will link your session at the station.':
    'आप फिर भी आगे बढ़ सकते हैं — स्टाफ़ स्टेशन पर आपका सत्र जोड़ देगा।',
  'Starting your contactless scan…': 'आपका बिना छुए स्कैन शुरू हो रहा है…',
  'Camera blocked by the browser': 'ब्राउज़र ने कैमरा रोक दिया है',
  'Camera access was denied for this site.': 'इस साइट के लिए कैमरा की अनुमति नहीं दी गई।',
  'Tap the camera or lock icon in the address bar.': 'एड्रेस बार में कैमरा या ताले वाले आइकन पर टैप करें।',
  'Set Camera to “Allow” for this site.': 'इस साइट के लिए कैमरा को “अनुमति दें” पर सेट करें।',
  'Come back here and tap Try again.': 'यहाँ वापस आकर “फिर कोशिश करें” पर टैप करें।',
  'Page is not secure': 'पेज सुरक्षित नहीं है',
  'Browsers only allow the camera on secure (https://) pages.':
    'ब्राउज़र सिर्फ़ सुरक्षित (https://) पेज पर कैमरा चलाने देते हैं।',
  'Open the app from its https:// address, or from localhost on this computer.':
    'ऐप को उसके https:// पते से, या इसी कंप्यूटर पर localhost से खोलें।',
  'No camera found': 'कोई कैमरा नहीं मिला',
  'This device has no camera the browser can reach.': 'इस डिवाइस में ऐसा कैमरा नहीं है जिसे ब्राउज़र इस्तेमाल कर सके।',
  'Connect a camera, or use a phone or laptop that has one.':
    'कैमरा लगाएँ, या कैमरा वाला फ़ोन या लैपटॉप इस्तेमाल करें।',
  'Then tap Try again.': 'फिर “फिर कोशिश करें” पर टैप करें।',
  'Camera is in use': 'कैमरा पहले से इस्तेमाल में है',
  'Another app or tab is already using the camera.': 'कोई दूसरा ऐप या टैब कैमरा इस्तेमाल कर रहा है।',
  'Close video calls, other camera apps or tabs.': 'वीडियो कॉल, दूसरे कैमरा ऐप या टैब बंद करें।',
  'Browser can’t use the camera': 'ब्राउज़र कैमरा इस्तेमाल नहीं कर सकता',
  'This browser does not support camera access.': 'यह ब्राउज़र कैमरा इस्तेमाल करने की सुविधा नहीं देता।',
  'Open the app in an up-to-date Chrome, Safari, Edge or Firefox.':
    'ऐप को नए Chrome, Safari, Edge या Firefox में खोलें।',
  'Camera could not start': 'कैमरा शुरू नहीं हो सका',
  'Something unexpected stopped the camera.': 'किसी अनचाही वजह से कैमरा रुक गया।',
  'Tap Try again.': '“फिर कोशिश करें” पर टैप करें।',
  'If it keeps happening, reload the page or restart the browser.':
    'बार-बार हो तो पेज दोबारा लोड करें या ब्राउज़र फिर से शुरू करें।',
  'Continue without camera': 'कैमरा के बिना आगे बढ़ें',
  'How to fix it': 'इसे कैसे ठीक करें',
  'Try again': 'फिर कोशिश करें',
  Cancel: 'रद्द करें',

  // report
  'Nurse check requested': 'नर्स से जाँच का अनुरोध',
  'A triage nurse will review your readings before your consultation. Two values are outside the normal range for age 54 — this is not a diagnosis.':
    'डॉक्टर से मिलने से पहले एक नर्स आपकी रीडिंग देखेगी। 54 साल की उम्र के लिए दो मान सामान्य सीमा से बाहर हैं — यह निदान नहीं है।',
  'Estimated review': 'अनुमानित समय',
  'about 4 min': 'लगभग 4 मिनट',
  'Consulting room 4': 'परामर्श कक्ष 4',
  'Key results': 'मुख्य परिणाम',
  'Heart rate': 'दिल की धड़कन',
  'Body temperature': 'शरीर का तापमान',
  'Breathing rate': 'साँस की दर',
  'Slightly elevated': 'थोड़ा बढ़ा हुआ',
  'Mild fever': 'हल्का बुखार',
  Optimal: 'उत्तम',
  'How many times your heart beats in a minute.': 'एक मिनट में आपका दिल कितनी बार धड़कता है।',
  'How warm your body is inside.': 'आपका शरीर अंदर से कितना गर्म है।',
  'How many breaths you take in a minute.': 'आप एक मिनट में कितनी साँसें लेते हैं।',
  'Faster than usual for you at rest — often stress, fever or recent activity. A nurse will recheck it.':
    'आराम की हालत में आपके लिए सामान्य से तेज़ — अक्सर तनाव, बुखार या हाल की गतिविधि से। नर्स इसे दोबारा जाँचेगी।',
  'A mild fever, 1.2 °C above your usual. Staff will confirm with a second thermometer.':
    'हल्का बुखार, आपके सामान्य से 1.2 °C ज़्यादा। स्टाफ़ दूसरे थर्मामीटर से पुष्टि करेगा।',
  'Steady, even breathing — nothing to do.': 'स्थिर, एक-सी साँस — कुछ करने की ज़रूरत नहीं।',
  'Encrypted clinical transmission · HIPAA & GDPR certified':
    'एन्क्रिप्टेड क्लिनिकल ट्रांसमिशन · HIPAA और GDPR प्रमाणित',
  'Share with your doctor': 'अपने डॉक्टर के साथ साझा करें',
  'Give your doctor this code. They enter it in Aura Screen to open your full report.':
    'यह कोड अपने डॉक्टर को दें। वे इसे ऑरा स्क्रीन में डालकर आपकी पूरी रिपोर्ट खोलेंगे।',
  'Code copied': 'कोड कॉपी हो गया',
  'Copy code': 'कोड कॉपी करें',
  'Send code and results…': 'कोड और परिणाम भेजें…',
  'Could not copy — please write the code down.': 'कॉपी नहीं हो सका — कृपया कोड लिख लें।',
  'The code only opens this report.': 'यह कोड सिर्फ़ यही रिपोर्ट खोलता है।',

  // timeline + session cards
  'Doctor:': 'डॉक्टर:',
  No: 'नहीं',
  Maybe: 'शायद',
  'Not needed': 'ज़रूरत नहीं',
  'Not applicable': 'लागू नहीं',
  sim: 'नकली',
  'Cognitive load · n-back': 'मानसिक मेहनत · n-back',
  'Rest → after exercise': 'आराम → कसरत के बाद',
  Resting: 'आराम',
  'Rest → city driving': 'आराम → शहर में गाड़ी चलाना',
  'Drinking a cold drink': 'ठंडा पेय पीना',
  'Face (action units)': 'चेहरा (भाव)',
  'Eye tracker': 'आँखों की ट्रैकिंग',
  'Pulse (PPG)': 'नब्ज़ (PPG)',
  'Skin conductance': 'त्वचा की नमी (चालकता)',
  Breathing: 'साँस',
  'Muscle (EMG)': 'मांसपेशी (EMG)',
  'Skin temperature': 'त्वचा का तापमान',

  // session result (ReadingsSummary, banner, glance)
  Normal: 'सामान्य',
  'Not normal': 'सामान्य नहीं',
  'No health reading': 'कोई स्वास्थ्य परिणाम नहीं',
  Fine: 'ठीक',
  Check: 'जाँचें',
  'Your session in one look': 'एक नज़र में आपका सत्र',
  'readings are fine': 'रीडिंग ठीक हैं',
  'Heart rate at rest': 'आराम के समय दिल की धड़कन',
  'Heart-rate variability': 'धड़कनों के बीच का अंतर (HRV)',
  'Breathing rate at rest': 'आराम के समय साँस की दर',
  "Body's response to harder tasks": 'कठिन काम पर शरीर की प्रतिक्रिया',
  'Heart rate after exercise': 'कसरत के बाद दिल की धड़कन',
  'Heart rate while driving': 'गाड़ी चलाते समय दिल की धड़कन',
  'Forehead temperature': 'माथे का तापमान',
  'Mouth temperature while drinking': 'पीते समय मुँह का तापमान',
  bpm: 'bpm',
  ms: 'ms',
  'breaths/min': 'साँसें/मिनट',
  '20 or more': '20 या ज़्यादा',
  'a rise is expected': 'बढ़ना अपेक्षित है',
  '31–35 (skin)': '31–35 (त्वचा)',
  'drops with a cold drink': 'ठंडे पेय से घटता है',
  'most rounds': 'ज़्यादातर राउंड',
  'How clearly your body reacted to mental effort — not a health measure':
    'मानसिक मेहनत पर आपका शरीर कितनी साफ़ प्रतिक्रिया देता है — यह स्वास्थ्य का माप नहीं है',
  'Rose by 17 bpm, as it should': '17 bpm बढ़ी, जैसा होना चाहिए',
  'Did not rise — the exercise was probably light': 'नहीं बढ़ी — कसरत शायद हल्की थी',
  'Higher than at rest — normal stress of city traffic': 'आराम से ज़्यादा — शहर के ट्रैफ़िक का सामान्य तनाव',
  'Cooled by 1.4 °C, then warmed back': '1.4 °C ठंडा हुआ, फिर वापस गर्म हुआ',
  'All your resting readings were in the healthy range.': 'आराम के समय आपकी सभी रीडिंग स्वस्थ सीमा में थीं।',
  'All your readings were in the healthy range.': 'आपकी सभी रीडिंग स्वस्थ सीमा में थीं।',
  'All your readings were in the healthy range. Your heart sped up in traffic, which is a normal reaction.':
    'आपकी सभी रीडिंग स्वस्थ सीमा में थीं। ट्रैफ़िक में आपकी धड़कन तेज़ हुई, जो सामान्य प्रतिक्रिया है।',
  "This recording can't say whether you are healthy. It shows how a cold drink cools the face.":
    'यह रिकॉर्डिंग नहीं बता सकती कि आप स्वस्थ हैं या नहीं। यह दिखाती है कि ठंडा पेय चेहरे को कैसे ठंडा करता है।',
  'How many times your heart beats in a minute while you sit still.':
    'बैठे-बैठे एक मिनट में आपका दिल कितनी बार धड़कता है।',
  'How fast your heart beats right after moving — it should go up.':
    'हिलने-डुलने के ठीक बाद दिल कितनी तेज़ धड़कता है — इसे बढ़ना चाहिए।',
  'How fast your heart beat in traffic; stress raises it for a while.':
    'ट्रैफ़िक में आपका दिल कितनी तेज़ धड़का; तनाव इसे कुछ देर बढ़ाता है।',
  'How much the gap between heartbeats changes. More change usually means a relaxed, healthy heart.':
    'दो धड़कनों के बीच का अंतर कितना बदलता है। ज़्यादा बदलाव का मतलब आमतौर पर शांत, स्वस्थ दिल है।',
  'How many breaths you take in a minute while sitting still.': 'बैठे-बैठे आप एक मिनट में कितनी साँसें लेते हैं।',
  'Your core temperature, measured by the thermal camera at the corner of the eye.':
    'आँख के कोने से थर्मल कैमरे द्वारा मापा गया शरीर का अंदरूनी तापमान।',
  'The skin temperature of your forehead, from the thermal camera.': 'थर्मल कैमरे से माथे की त्वचा का तापमान।',
  'How much a cold drink cooled the skin around your mouth.': 'ठंडे पेय ने मुँह के आसपास की त्वचा को कितना ठंडा किया।',
  'In how many rounds your body reacted the way the task asked: calm in easy rounds, working harder in hard ones.':
    'कितने राउंड में आपके शरीर ने काम के हिसाब से प्रतिक्रिया दी: आसान राउंड में शांत, कठिन में ज़्यादा मेहनत।',
  'See a doctor?': 'डॉक्टर को दिखाएँ?',
  'Your resting readings are in the healthy range.': 'आराम के समय आपकी रीडिंग स्वस्थ सीमा में हैं।',
  'No need to contact a doctor — the resting readings are within normal ranges.':
    'डॉक्टर से संपर्क की ज़रूरत नहीं — आराम के समय की रीडिंग सामान्य सीमा में हैं।',
  'No medical conclusion can be drawn — the temperatures are illustrative.':
    'कोई चिकित्सीय निष्कर्ष नहीं निकाला जा सकता — तापमान केवल उदाहरण हैं।',
  'This session at a glance': 'एक नज़र में यह सत्र',
  'How long you were recorded': 'आपकी रिकॉर्डिंग कितनी देर चली',
  'Measurements behind these results': 'इन परिणामों के पीछे के माप',
  'How each part of the session went': 'सत्र का हर हिस्सा कैसा रहा',
  Condition: 'स्थिति',
  'Should you contact a doctor?': 'क्या आपको डॉक्टर से संपर्क करना चाहिए?',
  'Your body clearly showed when the memory task got harder. This measures mental effort, not health.':
    'याददाश्त वाला काम कठिन होने पर आपके शरीर ने यह साफ़ दिखाया। यह मानसिक मेहनत का माप है, स्वास्थ्य का नहीं।',
  'Your body partly showed when the memory task got harder. This measures mental effort, not health.':
    'याददाश्त वाला काम कठिन होने पर आपके शरीर ने यह कुछ हद तक दिखाया। यह मानसिक मेहनत का माप है, स्वास्थ्य का नहीं।',
  "Your body's signals did not clearly show when the task got harder, so this reading is unreliable for you. This measures mental effort, not health.":
    'काम कठिन होने पर आपके शरीर के संकेतों ने यह साफ़ नहीं दिखाया, इसलिए यह रीडिंग आपके लिए भरोसेमंद नहीं है। यह मानसिक मेहनत का माप है, स्वास्थ्य का नहीं।',
  'Research prototype trained on 30 ADABase subjects; not validated for screening.':
    'शोध प्रोटोटाइप, 30 ADABase प्रतिभागियों पर प्रशिक्षित; जाँच के लिए प्रमाणित नहीं।',
  'Show all your data': 'अपना पूरा डेटा देखें',
  'Each line is one measurement over time; the shaded bands are the parts of the session. Drag across the chart to read every line at the same moment.':
    'हर रेखा समय के साथ एक माप है; छायांकित पट्टियाँ सत्र के हिस्से हैं। एक ही पल की हर रेखा पढ़ने के लिए चार्ट पर उँगली फेरें।',
  'Mental effort, all sensors (0–1)': 'मानसिक मेहनत, सभी सेंसर (0–1)',
  'Mental effort, from your face': 'मानसिक मेहनत, आपके चेहरे से',
  'Mental effort, from your eyes': 'मानसिक मेहनत, आपकी आँखों से',
  'Task difficulty (1–3)': 'काम की कठिनाई (1–3)',
  'Average mental effort (0–1)': 'औसत मानसिक मेहनत (0–1)',
  'Moments read as high effort': 'ज़्यादा मेहनत वाले पल',
  'Download all data': 'पूरा डेटा डाउनलोड करें',
  'Your doctor sees the full analysis. A screening aid, not a diagnosis.':
    'आपके डॉक्टर पूरा विश्लेषण देखते हैं। यह जाँच में मदद है, निदान नहीं।',
  'ADABase n-back recordings (Oppelt et al., 2023). Predictions are out-of-fold: the model never saw this subject during training.':
    'ADABase n-back रिकॉर्डिंग (Oppelt et al., 2023)। मॉडल ने प्रशिक्षण के दौरान इस व्यक्ति का डेटा कभी नहीं देखा।',
  Source: 'स्रोत',
  'Scroll or drag to move · pinch or ⌘-scroll to zoom': 'हिलाने के लिए स्क्रॉल करें या खींचें · ज़ूम के लिए पिंच करें',
  'Move across the graph to read every channel at the same instant.':
    'एक ही पल के सभी माप पढ़ने के लिए ग्राफ़ पर उँगली फेरें।',
  Fit: 'पूरा दिखाएँ',

  // other datasets' sessions (MCD-rPPG, drivedb, thermal)
  rPPG: 'कैमरा नब्ज़ (rPPG)',
  Thermal: 'थर्मल',
  EMG: 'EMG',
  Before: 'पहले',
  After: 'बाद में',
  Rest: 'आराम',
  City: 'शहर',
  Drinking: 'पीते समय',
  Forehead: 'माथा',
  Eyes: 'आँखें',
  Nose: 'नाक',
  Mouth: 'मुँह',
  '°C': '°C',
  'Nothing abnormal. Your heart and temperature were normal at rest, and the changes after exercise were the expected ones.':
    'कुछ भी असामान्य नहीं। आराम के समय आपका दिल और तापमान सामान्य थे, और कसरत के बाद के बदलाव अपेक्षित थे।',
  "Nothing abnormal. The signals were flagged because they changed a lot while driving, but those changes are the body's normal reaction to city traffic.":
    'कुछ भी असामान्य नहीं। गाड़ी चलाते समय संकेत बहुत बदले, पर ये बदलाव शहर के ट्रैफ़िक पर शरीर की सामान्य प्रतिक्रिया हैं।',
  'Nothing abnormal at rest. Your heart rate did not rise after exercise, most likely because the exercise was light — one sitting is not enough to say more.':
    'आराम के समय कुछ भी असामान्य नहीं। कसरत के बाद आपकी धड़कन नहीं बढ़ी, शायद कसरत हल्की थी — एक बार की रिकॉर्डिंग से ज़्यादा कहना मुश्किल है।',
  'Nothing abnormal. Your heart rate and temperature were both normal, and the camera reading agreed with the heart sensor.':
    'कुछ भी असामान्य नहीं। आपकी धड़कन और तापमान दोनों सामान्य थे, और कैमरे की रीडिंग दिल के सेंसर से मेल खाई।',
  'No health conclusion can be drawn from this recording. It shows what drinking something cold does to face temperatures.':
    'इस रिकॉर्डिंग से स्वास्थ्य के बारे में कोई निष्कर्ष नहीं निकाला जा सकता। यह दिखाती है कि ठंडा पीने से चेहरे का तापमान कैसे बदलता है।',
  'No abnormal findings at rest': 'आराम के समय कुछ असामान्य नहीं मिला',
  'Not assessable from this recording': 'इस रिकॉर्डिंग से आकलन संभव नहीं',
  'Normal resting heart rate': 'आराम के समय सामान्य धड़कन',
  'Normal temperature': 'सामान्य तापमान',
  'Heart-rate response to exercise': 'कसरत पर धड़कन की प्रतिक्रिया',
  'Healthy heart-rate variability': 'धड़कनों के अंतर (HRV) स्वस्थ',
  'Acute stress response while driving': 'गाड़ी चलाते समय तनाव की प्रतिक्रिया',
  'Camera reading': 'कैमरे की रीडिंग',
  'Thermal signature of drinking': 'पीने का थर्मल असर',
  'Muscle tension (EMG)': 'मांसपेशियों का तनाव (EMG)',
  'Muscle tension, EMG': 'मांसपेशियों का तनाव, EMG',
  'Heart rate (ECG)': 'दिल की धड़कन (ECG)',
  'Heart rate, ECG': 'दिल की धड़कन, ECG',
  'Heart rate, camera (POS)': 'दिल की धड़कन, कैमरा (POS)',
  'Camera vs ECG': 'कैमरा बनाम ECG',
  'Core temperature, thermal': 'अंदरूनी तापमान, थर्मल',
  'Camera signal quality': 'कैमरा सिग्नल की गुणवत्ता',
  'HRV (RMSSD), ECG': 'HRV (RMSSD), ECG',
  'Mean heart rate': 'औसत धड़कन',
  'Artifact beats': 'गड़बड़ धड़कनें',
  RMSSD: 'RMSSD',
  SDNN: 'SDNN',
  pNN50: 'pNN50',
  'Camera pulse (rPPG)': 'कैमरा नब्ज़ (rPPG)',
  'Simulated thermal video — prototype data': 'नकली थर्मल वीडियो — प्रोटोटाइप डेटा',
  'Heart rate from ECG': 'ECG से दिल की धड़कन',
  // n-back round names are the task's own names; kept as they are
  '1-back': '1-back',
  '2-back': '2-back',
  '3-back': '3-back',
  '1-back dual': '1-back dual',
  '2-back dual': '2-back dual',
  '3-back dual': '3-back dual',
  Pause: 'रोकें',
  Play: 'चलाएँ',
  'Colour map': 'रंग योजना',
  frame: 'फ़्रेम',
  "frames/s · hover the image for any pixel's temperature. Play, or move across the graph below — both show the same moment.":
    'फ़्रेम/सेकंड · किसी भी बिंदु का तापमान देखने के लिए तस्वीर पर कर्सर रखें। चलाएँ, या नीचे के ग्राफ़ पर उँगली फेरें — दोनों एक ही पल दिखाते हैं।',
  Inferno: 'इन्फ़र्नो',
  Grayscale: 'ग्रेस्केल',
  illustrative: 'केवल उदाहरण',
  'Screening aid, not a diagnosis. Heart rate uses the standard adult resting range (50–100 bpm); a camera reading outside it asks for a rescan before any doctor visit.':
    'जाँच में मदद, निदान नहीं। धड़कन के लिए वयस्कों की सामान्य आराम-सीमा (50–100 bpm) इस्तेमाल होती है; इससे बाहर कैमरे की रीडिंग पर डॉक्टर से पहले दोबारा स्कैन कहा जाता है।',
  "Prototype: ECG, thermal and EMG are simulated from this sitting's recorded vitals; only the camera pulse is measured. Screening aid, not a diagnosis. Heart rate uses the standard adult resting range (50–100 bpm); a camera reading outside it asks for a rescan before any doctor visit.":
    'प्रोटोटाइप: ECG, थर्मल और EMG इस रिकॉर्डिंग के दर्ज माप से बनाए गए हैं; सिर्फ़ कैमरा नब्ज़ असल में मापी गई है। जाँच में मदद, निदान नहीं।',
  "Face video of each sitting, at rest and after exercise. The camera pulse is real; ECG, thermal and EMG are simulated from the sitting's recorded vitals for the prototype.":
    'हर बार आराम के समय और कसरत के बाद चेहरे का वीडियो। कैमरा नब्ज़ असली है; ECG, थर्मल और EMG प्रोटोटाइप के लिए दर्ज माप से बनाए गए हैं।',
  "Healey & Picard, IEEE T-ITS 2005 · PhysioNet. ECG and EMG only, from Hans's ECG dashboard export.":
    'Healey & Picard, IEEE T-ITS 2005 · PhysioNet। सिर्फ़ ECG और EMG, हान्स के ECG डैशबोर्ड से।',
  "Temperatures are reconstructed from a false-colour palette and are illustrative. Converted from Hans's thermal dashboard export.":
    'तापमान रंगीन तस्वीर से निकाले गए हैं और केवल उदाहरण हैं। हान्स के थर्मल डैशबोर्ड से लिए गए।',
  'Zoom out': 'ज़ूम कम करें',
  'Zoom in': 'ज़ूम बढ़ाएँ',
  'Show the whole recording': 'पूरी रिकॉर्डिंग दिखाएँ',
  'Signal graph — arrow keys move through the recording':
    'सिग्नल ग्राफ़ — रिकॉर्डिंग में आगे-पीछे जाने के लिए तीर कुंजियाँ',
  'Why, and how to fix it': 'क्यों, और इसे कैसे ठीक करें',
  'Camera preview': 'कैमरा का दृश्य',
  Metric: 'माप',
  Change: 'बदलाव',
};

/** [pattern, (match, t) => Hindi] for text with numbers or names in it. `t` translates a captured part. */
export const HI_PATTERNS = [
  [/^Thermal frame (\d+) of (\d+)$/, (m) => `थर्मल फ़्रेम ${m[1]} / ${m[2]}`],
  [/^Loading (\d+) thermal frames…$/, (m) => `${m[1]} थर्मल फ़्रेम लोड हो रहे हैं…`],
  [/^(.+) \(simulated\)$/, (m, t) => `${t(m[1])} (नकली)`],
  [/^(\d+) bpm at rest by ECG \(normal ([\d–]+)\)$/, (m) => `ECG से आराम के समय ${m[1]} bpm (सामान्य ${m[2]})`],
  [
    /^([\d.]+) °C estimated core, from the thermal eye corner \(fever at ([\d.]+)\)$/,
    (m) => `आँख के कोने से थर्मल द्वारा अनुमानित अंदरूनी तापमान ${m[1]} °C (बुखार ${m[2]} पर)`,
  ],
  [
    /^\+(\d+) bpm after exercise — (.+)$/,
    (m) =>
      `कसरत के बाद +${m[1]} bpm — ${{ 'a normal rise': 'सामान्य बढ़त', 'little change; the bout may have been light': 'थोड़ा बदलाव; कसरत शायद हल्की थी' }[m[2]] ?? m[2]}`,
  ],
  [
    /^([\d.]+) → ([\d.]+) a\.u\. — rises after exercise, as expected$/,
    (m) => `${m[1]} → ${m[2]} a.u. — कसरत के बाद बढ़ता है, जैसा अपेक्षित`,
  ],
  [
    /^(\d+) bpm off the ECG — (.+)$/,
    (m) =>
      `ECG से ${m[1]} bpm का अंतर — ${{ 'the ECG fallback is what caught it': 'ECG विकल्प ने इसे पकड़ा' }[m[2]] ?? m[2]}`,
  ],
  [
    /^Within (\d+) bpm of the ECG — the camera alone would have got this right$/,
    (m) => `ECG से ${m[1]} bpm के भीतर — अकेला कैमरा भी सही होता`,
  ],
  [
    /^RMSSD (\d+) ms at rest \(below 20 ms is low\)$/,
    (m) => `आराम के समय RMSSD ${m[1]} ms (20 ms से कम कम माना जाता है)`,
  ],
  [
    /^Heart rate \+(\d+) bpm, HRV -(\d+)%, muscle tension ×(\d+) — the normal reaction to city traffic, not a disorder$/,
    (m) =>
      `धड़कन +${m[1]} bpm, HRV -${m[2]}%, मांसपेशी तनाव ×${m[3]} — शहर के ट्रैफ़िक पर सामान्य प्रतिक्रिया, कोई बीमारी नहीं`,
  ],
  [
    /^Mouth -([\d.]+) °C during drinking — explains the activity, not the person's health$/,
    (m) => `पीते समय मुँह -${m[1]} °C — यह गतिविधि बताता है, व्यक्ति का स्वास्थ्य नहीं`,
  ],
  [/^Session (\S+) · (.+)$/, (m, t) => `सत्र ${m[1]} · ${t(m[2])}`],
  [/^Station (\d+)$/, (m) => `स्टेशन ${m[1]}`],
  [/^Age (\d+)$/, (m) => `उम्र ${m[1]}`],
  [/^Biometric aura · (.+)$/, (m, t) => `बायोमेट्रिक ऑरा · ${t(m[1])}`],
  [/^(.+) · Routine check$/, (m) => `${m[1]} · नियमित जाँच`],
  [/^(\d+) sensors$/, (m) => `${m[1]} सेंसर`],
  [/^Given (.+)$/, (m) => `${m[1]} को दी गई`],
  [/^Queue #(.+)$/, (m) => `कतार #${m[1]}`],
  [/^Optimal · (.+)$/, (m) => `उत्तम · ${m[1]}`],
  [/^Signal ([\d.]+%)$/, (m) => `सिग्नल ${m[1]}`],
  [
    /^Normal is (.+?) — yours is (above|below|within) it\.$/,
    (m) => `सामान्य ${m[1]} है — आपकी ${{ above: 'इससे ज़्यादा', below: 'इससे कम', within: 'इसके अंदर' }[m[2]]} है।`,
  ],
  [/^Normal is (.+)\.$/, (m) => `सामान्य ${m[1]} है।`],
  [/^Share with doctor · Code (.+)$/, (m) => `डॉक्टर के साथ साझा करें · कोड ${m[1]}`],
  [
    /^(\d+) recorded sessions · open one to see what it showed and whether to see a doctor\.$/,
    (m) => `${m[1]} रिकॉर्ड किए गए सत्र · कोई सत्र खोलें और देखें उसमें क्या दिखा और क्या डॉक्टर को दिखाना है।`,
  ],
  [/^(.+) · (\d+) sessions?$/, (m) => `${m[1]} · ${m[2]} सत्र`],
  [/^(.+), session (\S+)$/, (m, t) => `${t(m[1])}, सत्र ${m[2]}`],
  [/^Normal: (.+)$/, (m, t) => `सामान्य: ${t(m[1])}`],
  [/^below ([\d.]+)$/, (m) => `${m[1]} से कम`],
  [/^of (\d+) rounds$/, (m) => `${m[1]} राउंड में से`],
  [/^of (\d+)$/, (m) => `${m[1]} में से`],
  [/^(\d+) min recorded · (\d+) sensors$/, (m) => `${m[1]} मिनट रिकॉर्डिंग · ${m[2]} सेंसर`],
  [/^(\d+) min$/, (m) => `${m[1]} मिनट`],
  [/^Sensors used: (.+)$/, (m, t) => `इस्तेमाल हुए सेंसर: ${m[1].split(', ').map(t).join(', ')}`],
  [/^Parts of the session: (.+)$/, (m, t) => `सत्र के हिस्से: ${m[1].split(', ').map(t).join(', ')}`],
  [
    /^Signal quality: (\w+)\. One recording is a snapshot of that day, not a diagnosis\.$/,
    (m) =>
      `सिग्नल की गुणवत्ता: ${{ good: 'अच्छी', fair: 'ठीक-ठाक', poor: 'कमज़ोर', illustrative: 'केवल उदाहरण' }[m[1]] ?? m[1]}। एक रिकॉर्डिंग उस दिन की झलक है, निदान नहीं।`,
  ],
  [
    /^([\d,]+) measurements from (\d+) sensors, as charts and a table$/,
    (m) => `${m[2]} सेंसर से ${m[1]} माप, चार्ट और तालिका में`,
  ],
  [
    /^Your (.+) (was|were) outside the normal range at rest\.$/,
    (m) => `आराम के समय आपकी ${hiVitals(m[1])} सामान्य सीमा से बाहर ${m[2] === 'was' ? 'थी' : 'थीं'}।`,
  ],
  [
    /^Mention your (.+) at your next check-up — one recording is not enough to be sure\.$/,
    (m) => `अगली जाँच में अपनी ${hiVitals(m[1])} के बारे में बताएँ — पक्का कहने के लिए एक रिकॉर्डिंग काफ़ी नहीं।`,
  ],
  [
    /^Your effort readings matched the task in (\d+) of (\d+) rounds$/,
    (m) => `${m[2]} में से ${m[1]} राउंड में आपकी मेहनत की रीडिंग काम से मेल खाई`,
  ],
  [/^(.+) · (easy|hard) round$/, (m) => `${m[1]} · ${m[2] === 'easy' ? 'आसान' : 'कठिन'} राउंड`],
  [
    /^Read as high effort (\d+) of (\d+) times — (as expected|not what the task asked for)$/,
    (m) =>
      `${m[2]} में से ${m[1]} बार ज़्यादा मेहनत पढ़ी गई — ${m[3] === 'as expected' ? 'जैसा अपेक्षित था' : 'काम के हिसाब से नहीं'}`,
  ],
];

// "heart rate and heart-rate variability" → Hindi, for the patterns above
const VITALS = {
  'heart rate': 'दिल की धड़कन',
  'heart-rate variability': 'धड़कनों का अंतर (HRV)',
  'breathing rate': 'साँस की दर',
};
function hiVitals(list) {
  return list
    .split(' and ')
    .map((v) => VITALS[v] ?? v)
    .join(' और ');
}
