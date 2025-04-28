# ElevenLabs Scribe STT Add-on for Home Assistant  
#readme.md  

This add-on integrates ElevenLabs Scribe Speech-to-Text into Home Assistant. It uses the Wyoming protocol for seamless integration with the Voice Assistant.  

## Overview  

ElevenLabs Scribe is a powerful speech-to-text service supporting multiple languages. This add-on enables ElevenLabs Scribe as an STT provider selectable in the Home Assistant Voice Assistant UI.  

## Installation  

1. Add this repository to your add-on repositories:  
   - Go to **Settings** → **Add-ons** → **Add-on Store**  
   - Click the menu in the top-right corner and select **Repositories**  
   - Add the following URL: `https://github.com/Dennis00dj/elevenlabs-stt-wyoming`  
   - Click **Add**  

2. Install the add-on:  
   - Search for "ElevenLabs Scribe STT" in the add-on list  
   - If not found, refresh the page once  
   - Click **Install**  

3. Configure the add-on:  
   - Enter your ElevenLabs API key  
   - Configure the port (default: 10300)  
   - Click **Save**  

4. Start the add-on:  
   - Click **Start**  

5. Add via Wyoming:  
   - Open **Services & Integrations**  
   - Add integration  
   - Select "Wyoming" under Voice Assistant in the Speech-to-Text section  

## Configuration  

| Option | Description | Default |  
|--------|-------------|---------|  
| `api_key` | Your ElevenLabs API key (required) | - |  
| `port` | Port for the Wyoming server | 10300 |  
| `model_id` | ElevenLabs model ID | scribe_v1 |  
| `debug` | Enable debug mode | false |  

## Usage with the Voice Assistant  

1. Go to **Settings** → **Voice Assistant**  
2. Select "Wyoming" as the STT engine  
3. Enter the following settings:  
   - Host: `localhost` (or your Home Assistant IP)  
   - Port: `10300` (or your configured port)  
4. Save the settings  
5. The Voice Assistant will now use ElevenLabs Scribe for speech recognition  

## Supported Languages  

- German (de)  
- English (en)  
- Spanish (es)  
- French (fr)  
- Italian (it)  
- Japanese (ja)  
- Portuguese (pt)  
- Dutch (nl)  

## Troubleshooting  

- Check the add-on logs to identify potential issues  
- Ensure your API key is valid  
- Verify the port is not in use by another application  

## License  

This project is licensed under the MIT License.
