# main.py
import io
import wave
import datetime
import json
import aiofiles
import aiosmtplib
import scipy

from loguru import logger
from typing import Dict
from pathlib import Path
from fastapi import WebSocket
from email.message import EmailMessage

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.runner import PipelineRunner
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat_flows import FlowArgs, FlowManager, FlowResult, FlowsFunctionSchema, NodeConfig
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.frames.frames import Frame
from pipecat.audio.vad.vad_analyzer import VADParams
from dotenv import load_dotenv
import os

class PatientInfo(FlowResult):
    full_name: str
    age: int
    dob: str
    insurance_info: str
    referral: str
    complaint: str
    address: str
    contact: str
    appointment: str


async def send_email(to_email: str, subject: str, body: str):
    logger.debug("Inside send_email function")
    load_dotenv()

    pwd = os.getenv("GMAIL_APP_PWD")
    message = EmailMessage()
    message["From"] = "annvthomas23@gmail.com"
    message["To"] = to_email
    message["Subject"] = "Appointment Reminder"
    message.set_content(body)
    logger.debug("After setting variables")

    # Gmail SMTP example — use your email server details here
    try:
        logger.debug("Trying to send email")
        await aiosmtplib.send(
            message,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username="annvthomas23@gmail.com",
            password=pwd,  # MUST be an app password if 2FA is on
        )
        logger.info(f"Email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

def save_user_info(user_data: dict, filename: str = "user_info.json"):
    """Save user info to a JSON file."""
    file_path = Path(filename)
    logger.debug(f"Got the file path")

    if file_path.exists():
        logger.debug(f"File path exists")
        with open(file_path, "r") as f:
            logger.debug(f"File opened")
            existing_data = json.load(f)
            logger.debug(f"Existing json opened")
    else:
        logger.debug(f"File path doesn't exist")
        existing_data = []
        logger.debug(f"Created array")

    existing_data.append(user_data)
    logger.debug(f"Append new data to existing data")

    with open(file_path, "w") as f:
        json.dump(existing_data, f, indent=2)
        logger.debug(f"Dump data back into json")

async def collect_name(args: FlowArgs) -> PatientInfo:
    first_name = args["first_name"]
    last_name = args["last_name"]
    full_name = f"{first_name} {last_name}"

    logger.debug(f"Created full name")
    patient = args.get("patient_info") 
    if isinstance(patient, dict):
        patient = PatientInfo(**patient)
    elif patient is None:
        patient = PatientInfo()
    logger.debug(f"Created patient object]")
    logger.debug(patient)
    logger.debug(args)


    # patient.full_name = full_name
    # logger.debug(f"Created name in patient object")
    # args["patient_info"] = patient
    # logger.debug(f"Created added patient object to args")

    name = {
        "first_name": first_name,
        "last_name": last_name,
    }

    args["name"] = name
    save_user_info(args["name"])
    logger.debug(f"collect_name handler executing with name: {name}")

    return PatientInfo(name=f"{first_name} {last_name}")

async def collect_dob(args: FlowArgs) -> PatientInfo:
    dob = args["dob"]
    logger.debug(f"collect_dob handler executing with dob: {dob}")
    logger.debug(args)
    # save_user_info(args)
    return PatientInfo(dob=dob)

async def collect_insurance_info(args: FlowArgs) -> PatientInfo:
    payer = args["payer"]
    insurance_id = args["id"]

    insurance_info = {
        "payer": payer,
        "id": insurance_id,
    }

    logger.debug(f"collect_insurance_info handler executing with insurance_info: {insurance_info}")

    args["insurance_info"] = insurance_info

    return PatientInfo(insurance_info=f"payer: {payer}, id: {insurance_id}")

async def collect_referral(args: FlowArgs) -> PatientInfo:
    referral = args.get("referral", "").strip()
    
    if referral:
        logger.info(f"Referral received: {referral}")
    else:
        logger.info("No referral provided")

    save_user_info(args)
    return PatientInfo(referral=referral)

async def collect_complaint(args: FlowArgs) -> PatientInfo:
    complaint = args["complaint"]
    logger.debug(f"collect_complaint handler executing with dob: {complaint}")
    # save_user_info(args)
    return PatientInfo(complaint=complaint)

async def collect_complaint(args: FlowArgs) -> PatientInfo:
    complaint = args["complaint"]
    logger.debug(f"collect_complaint handler executing with dob: {complaint}")
    # save_user_info(args)
    return PatientInfo(complaint=complaint)
async def collect_address(args: FlowArgs) -> PatientInfo:
    address = args["address"]
    logger.debug(f"collect_address handler executing with dob: {address}")
    # save_user_info(args)
    return PatientInfo(address=address)

async def collect_contact(args: FlowArgs) -> PatientInfo:
    phone_number = args["phone_number"]
    email = args["email"]

    contact = {
        "phone_number": phone_number,
        "email": email,
    }

    logger.debug(f"collect_contact handler executing with dob: {contact}")
    save_user_info(args)
    return PatientInfo(contact=f"phone_number: {phone_number}, email: {email}")

async def collect_appointment(args: FlowArgs) -> PatientInfo:
    appointment = args["appointment"]    
    logger.debug(f"collect_appointment handler executing with dob: {appointment}")
    save_user_info(args)
    return PatientInfo(appointment=appointment)

async def create_email(args: FlowArgs):
    logger.debug("create_email function executing")
    
    try:
        with open("user_info.json", "r") as f:
            user_data = json.load(f)

            latest_name = "there"
            for entry in user_data:
                if "first_name" in entry and "last_name" in entry:
                    latest_name = f"{entry['first_name']} {entry['last_name']}"
                    break

            appointment_info = next(
                (entry["appointment"] for entry in user_data if "appointment" in entry),
                None
            )

            user_email = next(
                (entry["email"] for entry in user_data if "email" in entry),
                None
            )
    except Exception as e:
        logger.error(f"Error loading user_info.json: {e}")
        latest_name = "there"

    # Compose and send email
    # user_email = "annvthomas23@gmail.com"
    subject = "Appointment Confirmation"
    body = (f"Hi {latest_name},\n\n"
            "I'm reaching out to confirm that we have scheduled your appointment "
            f"with {appointment_info}"
            "\n\nBest,\nAssort Health"
    )
    logger.debug("Before send_email function")
    await send_email(user_email, subject, body)
    logger.debug("After send_email function")

    file_path = Path("user_info.json")
    if file_path.exists():
        file_path.unlink()
    return {"status": "completed"}



# Transition callbacks and handlers
async def handle_name_collection(args: Dict, result: PatientInfo, flow_manager: FlowManager):
    flow_manager.state["name"] = result["name"]
    await flow_manager.set_node("dob", create_dob_status_node())

async def handle_dob_collection(args: Dict, result: PatientInfo, flow_manager: FlowManager):
    flow_manager.state["dob"] = result["dob"]
    await flow_manager.set_node("insurance_info", create_insurance_info_node())

async def handle_insurance_info_collection(args: Dict, result: PatientInfo, flow_manager: FlowManager):
    flow_manager.state["insurance_info"] = result["insurance_info"]
    await flow_manager.set_node("referral", create_referral_node())

async def handle_referral_collection(args: Dict, result: PatientInfo, flow_manager: FlowManager):
    flow_manager.state["referral"] = result["referral"]
    await flow_manager.set_node("complaint", create_complaint_node())

async def handle_complaint_collection(args: Dict, result: PatientInfo, flow_manager: FlowManager):
    flow_manager.state["complaint"] = result["complaint"]
    await flow_manager.set_node("address", create_address_node())

async def handle_address_collection(args: Dict, result: PatientInfo, flow_manager: FlowManager):
    flow_manager.state["address"] = result["address"]
    await flow_manager.set_node("contact", create_contact_node())

async def handle_contact_collection(args: Dict, result: PatientInfo, flow_manager: FlowManager):
    flow_manager.state["contact"] = result["contact"]
    await flow_manager.set_node("appointment", create_appointment_node())

async def handle_appointment_collection(args: Dict, result: PatientInfo, flow_manager: FlowManager):
    flow_manager.state["appointment"] = result["appointment"]
    await flow_manager.set_node("create_email", create_email_node())


async def handle_create_email(args: Dict, result: PatientInfo, flow_manager: FlowManager):
    logger.debug("handle create email function executing")
    await flow_manager.set_node("end", create_end_node())


# Node configurations using FlowsFunctionSchema
def create_initial_node() -> NodeConfig:
    """Create the initial node asking for name."""
    return {
        "role_messages": [
            {
                "role": "system",
                "content":
                ""
            }
        ],
        "task_messages": [
            {
                "role": "system",
                "content": 
                "You are Annie, an agent for a company called Assort Health Services. "
                "Your job is to collect important information from the user before their doctor visit. "
                "Your tone should be warm and kind."
                "You should address the user by their first name and be polite and professional. "
                "You're not a medical professional, so you shouldn't provide any advice." 
                "Don't make assumptions about what values to plug into functions." 
                "Ask for clarification if a user response is ambiguous."
                "The patient should be calling to schedule an appointment but they may get distracted and talk/ask about other things."
                "If that happens, answer politely and try to keep them on track with the questions you have for them."

                
                "Your responses will be converted to audio, so avoid special characters. "
                "Always wait for customer responses before calling functions. "
                "Only call functions after receiving relevant information from the customer."
                "Never explicitly mention functions or apis to the user."

                "Introduce yourself and ask the patient for their first and last name."
                "Make sure you get both a first and last name from the patient."
                "If you are unsure how to spell their name or they have a name that commonly has multiple spellings, "
                "ask them to spell it out for you."
                "Wait for their response before calling the function. "
                "Only call the function after they provide their name."
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="collect_name",
                description="Record patient's name",
                properties={
                    "first_name": {
                        "type": "string",
                    },
                    "last_name": {
                        "type": "string",
                    }
                },
                required=["first_name", "last_name"],
                handler=collect_name,
                transition_callback=handle_name_collection,
            )
        ],
    }

def create_dob_status_node() -> NodeConfig:
    """Create the node for asking for dob."""
    return {
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Ask the patient for their date of birth. "
                    "Wait for their response before calling the function. "
                    "Only call the function after they provide their date of birth."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="collect_dob",
                description="Record patient's dob",
                properties={"dob": {"type": "string"}},
                required=["dob"],
                handler=collect_dob,
                transition_callback=handle_dob_collection,
            )
        ],
    }
def create_insurance_info_node() -> NodeConfig:
    """Create node for insurance info."""
    return {
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Ask for the patient's insurance information."
                    "This should include both payer name and ID."
                    "Wait for their response before the function."
                    "Only call the function after they provide their information."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="collect_insurance_info",
                description="Record insurance info after patient provides it",
                properties={
                    "payer": {
                        "type": "string",
                        "description": "The name of the insurance provider (e.g., Blue Cross, Aetna)"
                    },
                    "id": {
                        "type": "string",
                        "description": "The member or insurance ID number"
                    }
                },
                required=["payer", "id"],
                handler=collect_insurance_info,
                transition_callback=handle_insurance_info_collection,
            )
        ],
    }

def create_referral_node() -> NodeConfig:
    """Create node for referral."""
    return {
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Ask if the patient has a referral."
                    "If so, ask them to which physician"
                    "Wait for their response before the function."
                    "Only call the function after they provide their information."
                    "Enter the doctor's name or a blank if there was no referral."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="collect_referral",
                description="Record insurance referral info — either a doctor's name or blank if there was no referral.",
                properties={"referral": {"type": "string"}},
                required=["referral"],
                handler=collect_referral,
                transition_callback=handle_referral_collection,
            )
        ],
    }

def create_complaint_node() -> NodeConfig:
    """Create chief medical complaint/reason they are coming in."""
    return {
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Ask the patient for the reason they would like to come in for an appointment."
                    "There response should be some kind of medical complaint."
                    "Wait for their response before the function."
                    "Only call the function after they provide their information."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="collect_complaint",
                description="Record complaint info after patient provides it",
                properties={"complaint": {"type": "string"}},
                required=["complaint"],
                handler=collect_complaint,
                transition_callback=handle_complaint_collection,
            )
        ],
    }

def create_address_node() -> NodeConfig:
    """Create node for address."""
    return {
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Ask the patient to provide their address."
                    "Validate the address they provide."
                    "If it is invalid or missing fields, ask them for missing fields or to re-state their address."
                    "Fields include street address, city, and state."
                    "Make sure they give a complete and valid address before moving on to the function."
                    "Only call the function after they provide their information."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="collect_address",
                description="Record adress after patient provides it",
                properties={"address": {"type": "string"}},
                required=["address"],
                handler=collect_address,
                transition_callback=handle_address_collection,
            )
        ],
    }

def create_contact_node() -> NodeConfig:
    """Create node for contact info."""
    return {
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Ask the patient to provide their phone number and email."
                    "The email address should get saved in a proper email address format."
                    "Make sure to get a valid email address from them (ex: name@somemail.com)."
                    "Always ask them to repeat the spelling of the email back to you to make sure it's accurate."
                    "Wait for their response before the function."
                    "Only call the function after they provide their information."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="collect_contact",
                description="Record contact info after patient provides it",
                properties={
                    "phone_number": {
                        "type": "string",
                        "description": "The phone number"
                    },
                    "email": {
                        "type": "string",
                        "description": "The email address"
                    }
                },
                required=["phone_number", "email"],
                handler=collect_contact,
                transition_callback=handle_contact_collection,
            )
        ],
    }

def create_appointment_node() -> NodeConfig:
    """Create the node for creating an appointment."""
    return {
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Your text will be translated to speech so don't use any asterisks, bullets or other special characters."
                    "Next set up an appointment for the patient."
                    "If the patient provided a referral name, the appointment should be with that doctor."
                    "Otherwise, provide them with three doctor names for them to choose from."
                    "Once they select a doctor, provide 4 potential appoinment times in the following week (next week)."
                    "The appointment times should be within reasonable work hours."
                    "Today is Wednesday, May 21st for reference."
                    "State the potential times in a sentence like you would speak them instead of as a bulletted list."
                    "Provide the actual date and time (not just the day of the week)"
                    "If none of those times work for the patient, provide additional times in the week after."
                    "Once the patient finds a time that is suitable, go ahead and move on."
                    "You should save their answer as a string in the following format:"
                    "appointment with Dr. ___ on _____."
                    "where the first blank is where the doctor's name should go and the second is the date and time the patient selects."
                    "This applies whether or not the doctor is from a referral or not."

                    "Wait for their response before calling the function. "
                    "Only call the function after they provide their information."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="collect_appointment",
                description="Record appointment time.",
                properties={"appointment": {"type": "string"}},
                required=["appointment"],
                handler=collect_appointment,
                transition_callback=handle_appointment_collection,
            )
        ],
    }

def create_email_node() -> NodeConfig:
    """Create the final node."""
    return {
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Let the patient know that their appoinment has been scheduled (if they scheduled one)."
                    "Make sure to call the create_email function."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="create_email",
                description="Send the patient an email",
                properties={},
                required=[],
                handler=create_email,
                transition_callback=handle_create_email,
            ),
        ],
    }


def create_end_node() -> NodeConfig:
    """Create the final node."""
    return {
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Let the patient know that their appoinment has been scheduled (if they scheduled one)."
                    "Thank them and politely end the conversation."
                    "Wait for the user to respond/acknoledge before hanging up."
                    "Make sure to call the end_conversation function at the end no matter what."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="end_conversation",
                description="End the conversation",
                properties={},
                required=[],
            ),
        ],
        "post_actions": [{"type": "end_conversation"}],
    }


async def save_audio(server_name: str, audio: bytes, sample_rate: int, num_channels: int):
    if len(audio) > 0:
        filename = (
            f"{server_name}_recording_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        )
        with io.BytesIO() as buffer:
            with wave.open(buffer, "wb") as wf:
                wf.setsampwidth(2)
                wf.setnchannels(num_channels)
                wf.setframerate(sample_rate)
                wf.writeframes(audio)
            async with aiofiles.open(filename, "wb") as file:
                await file.write(buffer.getvalue())
        logger.info(f"Merged audio saved to {filename}")
    else:
        logger.info("No audio data to save")

async def test_bot(websocket_client: WebSocket, stream_sid: str, call_sid: str, testing: bool):

    
    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=serializer,
        ),
    )

    load_dotenv()

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    llm = GoogleLLMService(api_key=os.getenv("GOOGLE_API_KEY"))


    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    context = OpenAILLMContext()
    context_aggregator = llm.create_context_aggregator(context)

    audiobuffer = AudioBufferProcessor(user_continuous_stream=not testing)


    pipeline = Pipeline(
        [
            transport.input(),  
            stt,  
            context_aggregator.user(),
            llm,  
            tts,  
            transport.output(),  
            audiobuffer,  
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            allow_interruptions=True,
        ),
    )

    flow_manager = FlowManager(
        task=task,
        llm=llm,
        context_aggregator=context_aggregator,
        tts=tts,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Start recording.
        await audiobuffer.start_recording()

        await flow_manager.initialize()
        await flow_manager.set_node("initial", create_initial_node())

   
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await task.cancel()

    @audiobuffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        server_name = f"server_{websocket_client.client.port}"
        await save_audio(server_name, audio, sample_rate, num_channels)


    runner = PipelineRunner(handle_sigint=False, force_gc=True)

    await runner.run(task)