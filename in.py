import os
from instagrapi import Client

def main():
    print("==========================================")
    print("      ⚡ Instagram Automation Tool ⚡      ")
    print("==========================================")
    
    # Credentials
    username = input("Enter your Instagram Username: ").strip()
    password = input("Enter your Instagram Password: ").strip()
    
    client = Client()
    
    print("\n⏳ Logging into Instagram...")
    try:
        # Session file check taaki baar-bar OTP/Login na karna pade
        session_file = f"{username}_session.json"
        if os.path.exists(session_file):
            client.load_settings(session_file)
            
        client.login(username, password)
        client.dump_settings(session_file)
        print("✅ Login Successful!\n")
        
    except Exception as e:
        print(f"❌ Login Failed: {str(e)}")
        return

    while True:
        print("\n--- Select Operation ---")
        print("1. Send Likes on Post (Post Link daalo)")
        print("2. Follow a User (Target Username daalo)")
        print("3. Exit")
        
        choice = input("Enter choice (1/2/3): ").strip()
        
        if choice == "1":
            post_url = input("Enter Instagram Post Link: ").strip()
            try:
                media_id = client.media_pk_from_url(post_url)
                client.media_like(media_id)
                print("❤️ Successfully Liked the Post!")
            except Exception as e:
                print(f"❌ Error liking post: {str(e)}")
                
        elif choice == "2":
            target_user = input("Enter Target Username (without @): ").strip()
            try:
                user_id = client.user_id_from_username(target_user)
                client.user_follow(user_id)
                print(f"👤 Successfully Followed @{target_user}!")
            except Exception as e:
                print(f"❌ Error following user: {str(e)}")
                
        elif choice == "3":
            print("Exiting... Bye bhai!")
            break
        else:
            print("❌ Invalid choice, dubara try karo!")

if __name__ == "__main__":
    main()

